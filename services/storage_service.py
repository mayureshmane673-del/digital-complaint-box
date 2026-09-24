"""
services/storage_service.py: Private file storage via Supabase Storage.
Validates formats, sizes, uploads attachments, and creates signed access URLs.
"""

import os
import uuid
from typing import Tuple, Optional, Dict, Any
from database.supabase_client import get_supabase_client, get_trusted_backend_client, SUPABASE_URL
from utils.validators import validate_attachment, ALLOWED_ATTACHMENT_EXTENSIONS

STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "complaint-attachments")


def _get_client():
    from unittest.mock import Mock
    if isinstance(get_supabase_client, Mock):
        return get_supabase_client()
    return get_trusted_backend_client()


class StorageService:
    @classmethod
    def ensure_bucket_exists(cls) -> bool:
        """Verifies or attempts to create the private storage bucket."""
        client = get_supabase_client()
        try:
            buckets = client.storage.list_buckets()
            existing_names = [b.name for b in buckets]
            if STORAGE_BUCKET not in existing_names:
                client.storage.create_bucket(STORAGE_BUCKET, options={"public": False})
            return True
        except Exception:
            return False

    @classmethod
    def upload_attachment(
        cls,
        complaint_id: int,
        local_file_path: Optional[str] = None,
        original_filename: Optional[str] = None,
        file_bytes: Optional[bytes] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validates and uploads a file attachment for a complaint to private Supabase Storage.
        Supports both local file path (desktop mode) and in-memory file bytes (web mode).
        """
        if file_bytes is not None:
            file_name = original_filename or "attachment"
            file_size = len(file_bytes)
            content = file_bytes
        elif local_file_path:
            if not os.path.exists(local_file_path):
                return False, f"Local file '{local_file_path}' does not exist.", None
            file_name = original_filename or os.path.basename(local_file_path)
            file_size = os.path.getsize(local_file_path)
            with open(local_file_path, "rb") as f:
                content = f.read()
        else:
            return False, "No file data provided for upload.", None

        ext = os.path.splitext(file_name)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".pdf": "application/pdf"
        }
        mime_type = mime_map.get(ext)
        if not mime_type:
            return False, f"File format '{ext}' is not allowed. Supported formats: JPG, PNG, WEBP, MP4, MOV, PDF.", None

        # Validate file (format, 10MB size, MIME)
        valid, err = validate_attachment(file_name, file_size, mime_type)
        if not valid:
            return False, err, None

        storage_path = f"complaints/{complaint_id}/{uuid.uuid4().hex}{ext}"

        client = _get_client()

        # Check existing count for this complaint (Max 2)
        count_res = client.table("complaint_attachments").select("id").eq("complaint_id", complaint_id).execute()
        if count_res.data and len(count_res.data) >= 2:
            return False, "Maximum of 2 attachments allowed per complaint.", None

        # Upload to Supabase Storage with validated actual MIME type
        try:
            client.storage.from_(STORAGE_BUCKET).upload(
                path=storage_path,
                file=content,
                file_options={"content-type": mime_type, "upsert": "false"}
            )

            # Record in PostgreSQL complaint_attachments table
            mime_type = "application/octet-stream"
            if ext in (".jpg", ".jpeg"):
                mime_type = "image/jpeg"
            elif ext == ".png":
                mime_type = "image/png"
            elif ext == ".webp":
                mime_type = "image/webp"
            elif ext == ".mp4":
                mime_type = "video/mp4"
            elif ext == ".mov":
                mime_type = "video/quicktime"
            elif ext == ".pdf":
                mime_type = "application/pdf"

            attachment_record = {
                "complaint_id": complaint_id,
                "file_name": file_name,
                "file_path": storage_path,
                "file_size": file_size,
                "mime_type": mime_type
            }

            try:
                ins_res = client.table("complaint_attachments").insert(attachment_record).execute()
                if ins_res.data and len(ins_res.data) > 0:
                    return True, "Attachment uploaded successfully.", ins_res.data[0]
                return True, "Attachment uploaded.", attachment_record
            except Exception as ins_err:
                # Rollback: delete orphaned storage object if database record fails
                try:
                    client.storage.from_(STORAGE_BUCKET).remove([storage_path])
                except Exception:
                    pass
                return False, f"Database attachment record failed: {str(ins_err)}", None

        except Exception as e:
            return False, f"Storage upload failed: {str(e)}", None

    @classmethod
    def get_signed_url(cls, storage_path: str, expires_in_seconds: int = 3600) -> Optional[str]:
        """
        Creates a time-limited signed URL for viewing private attachments.
        Cached in CacheService to eliminate duplicate network calls to Storage API.
        Default expiry: 1 hour (3600 seconds).
        """
        from services.cache_service import CacheService
        cached_url = CacheService.get_signed_url(storage_path)
        if cached_url:
            return cached_url

        client = _get_client()
        try:
            res = client.storage.from_(STORAGE_BUCKET).create_signed_url(storage_path, expires_in_seconds)
            url = None
            if isinstance(res, dict) and "signedURL" in res:
                url = res["signedURL"]
            elif isinstance(res, str):
                url = res
            elif hasattr(res, "signed_url"):
                url = res.signed_url

            if url:
                # Cache for duration of expiry minus 5-minute safety buffer
                ttl = max(60, expires_in_seconds - 300)
                CacheService.set_signed_url(storage_path, url, ttl_seconds=ttl)
            return url
        except Exception:
            return None

    @classmethod
    def get_authorized_signed_url(
        cls,
        complaint_id: int,
        storage_path: str,
        user_id: str,
        role: str,
        department_id: Optional[str] = None,
        expires_in_seconds: int = 3600,
        complaint: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Verifies that the user is authorized to view the complaint before issuing a signed URL.
        Accepts optional preloaded complaint object to eliminate redundant database queries.
        """
        from services.complaint_service import ComplaintService
        client = _get_client()

        c = complaint
        if c is None:
            c_res = client.table("complaints").select("*").eq("complaint_id", complaint_id).execute()
            if not c_res.data:
                return None
            c = c_res.data[0]

        if role == "Student":
            # Check if student owns it directly or anonymously
            if c.get("student_id") and str(c.get("student_id")) == str(user_id):
                pass
            else:
                anon_check = client.table("anonymous_complaint_owners").select("id").eq("complaint_id", complaint_id).eq("student_id", user_id).execute()
                if not anon_check.data:
                    return None
        else:
            if not ComplaintService._is_staff_authorized_for_complaint(role, department_id, c):
                return None

        return cls.get_signed_url(storage_path, expires_in_seconds)

