"""
services/cache_service.py: High-performance in-memory reference and metadata caching layer.
Thread-safe, lazy-loading, with TTL-based expiration and targeted invalidation.
Eliminates repeated Supabase round trips for static and semi-static data.
"""

import time
import threading
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict


class CacheService:
    _lock = threading.RLock()

    # Cached datasets
    _departments: Optional[List[Dict[str, Any]]] = None
    _departments_by_code: Optional[Dict[str, Dict[str, Any]]] = None
    _departments_by_id: Optional[Dict[str, Dict[str, Any]]] = None
    _special_dept_ids: Dict[str, str] = {}

    _categories: Optional[List[Dict[str, Any]]] = None
    _locations: Optional[List[Dict[str, Any]]] = None
    _subcategories_by_cat: Optional[Dict[str, List[Dict[str, Any]]]] = None

    _security_codes_cache: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}

    # Signed URL cache: storage_path -> (expiry_timestamp, signed_url)
    _signed_urls: Dict[str, Tuple[float, str]] = {}

    # Dashboard metrics cache: (role, dept_id) -> (expiry_timestamp, metrics_dict)
    _metrics_cache: Dict[Tuple[str, Optional[str]], Tuple[float, Dict[str, Any]]] = {}

    # Department breakdown cache: expiry_timestamp, list of breakdown dicts
    _dept_breakdown_cache: Optional[Tuple[float, List[Dict[str, Any]]]] = None

    # Unread notification count cache: (user_id, role, dept_id) -> (expiry_timestamp, count)
    _unread_count_cache: Dict[Tuple[str, str, Optional[str]], Tuple[float, int]] = {}

    # -------------------------------------------------------------------------
    # REFERENCE DATA: DEPARTMENTS
    # -------------------------------------------------------------------------
    @classmethod
    def get_departments(cls, force_refresh: bool = False) -> List[Dict[str, Any]]:
        with cls._lock:
            if cls._departments is not None and not force_refresh:
                return cls._departments

            from database.supabase_client import get_trusted_backend_client, get_supabase_client
            client = get_trusted_backend_client() or get_supabase_client()
            try:
                res = client.table("departments").select("id, code, name").execute()
                depts = res.data or []
            except Exception:
                depts = []

            if not depts:
                # Fallback default departments
                depts = [
                    {"id": "f4e141ef-14ca-44e4-a1ed-051ee0525419", "code": "CSE", "name": "Computer Science and Engineering"},
                    {"id": "06059c36-8a03-4f9e-9086-1d116a3bc533", "code": "AIDS", "name": "Artificial Intelligence and Data Science"},
                    {"id": "a90df03a-3243-4ce2-bdf1-3312c5b3d6f1", "code": "E&TC", "name": "Electronics and Telecommunication Engineering"},
                    {"id": "d05fe7ee-bfcf-41c3-8be2-72abcb71b802", "code": "MECH", "name": "Mechanical Engineering"},
                    {"id": "517fc5e3-cf9d-4340-9a4f-a2e6f4770176", "code": "Civil", "name": "Civil Engineering"},
                    {"id": "d7fda5ae-09ef-4324-9048-7b721bf89bf7", "code": "GEN", "name": "General Department"},
                    {"id": "955f5c89-535f-4324-a7e9-7e8762380ac9", "code": "LIB", "name": "Library Department"}
                ]

            cls._departments = depts
            cls._departments_by_code = {d["code"].strip().upper(): d for d in depts if d.get("code")}
            cls._departments_by_id = {str(d["id"]): d for d in depts if d.get("id")}
            for d in depts:
                c = d.get("code", "").strip().upper()
                if c:
                    cls._special_dept_ids[c] = str(d["id"])

            return cls._departments

    @classmethod
    def get_special_dept_id(cls, code: str) -> Optional[str]:
        clean_code = code.strip().upper()
        with cls._lock:
            if clean_code in cls._special_dept_ids:
                return cls._special_dept_ids[clean_code]

            # Populate departments
            cls.get_departments()
            if clean_code in cls._special_dept_ids:
                return cls._special_dept_ids[clean_code]

            if clean_code == "GEN":
                return "d7fda5ae-09ef-4324-9048-7b721bf89bf7"
            if clean_code == "LIB":
                return "955f5c89-535f-4324-a7e9-7e8762380ac9"
            return None

    # -------------------------------------------------------------------------
    # REFERENCE DATA: CATEGORIES, SUBCATEGORIES, LOCATIONS
    # -------------------------------------------------------------------------
    @classmethod
    def get_categories_and_subcategories(cls, force_refresh: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """
        Returns (categories, subcategories_by_cat, locations) precomputed and cached.
        """
        with cls._lock:
            if cls._categories is not None and cls._subcategories_by_cat is not None and cls._locations is not None and not force_refresh:
                return cls._categories, cls._subcategories_by_cat, cls._locations

            from models.complaint import PRACTICAL_SUBCATEGORIES, get_default_priority
            from database.supabase_client import get_trusted_backend_client, get_supabase_client
            client = get_trusted_backend_client() or get_supabase_client()

            # 1. Categories
            try:
                cat_res = client.table("categories").select("id, name").eq("is_active", True).execute()
                categories = cat_res.data or []
            except Exception:
                categories = []

            if not categories:
                categories = [{"id": name.lower().replace(" ", "_"), "name": name} for name in PRACTICAL_SUBCATEGORIES.keys()]

            # 2. Locations
            try:
                loc_res = client.table("locations").select("id, name").eq("is_active", True).execute()
                locations = loc_res.data or []
            except Exception:
                locations = []

            # 3. Subcategories from DB (active only)
            try:
                sub_res = client.table("subcategories").select("id, name, category_id").eq("is_active", True).execute()
                all_subs = sub_res.data or []
            except Exception:
                all_subs = []

            cat_id_to_name = {str(c["id"]): c["name"] for c in categories}
            cat_name_to_id = {c["name"].strip().lower(): str(c["id"]) for c in categories}

            # Group DB subcategories by normalized category name
            db_subs_by_catname = defaultdict(dict)
            for s in all_subs:
                cid = str(s.get("category_id"))
                cname = cat_id_to_name.get(cid)
                if cname:
                    sname = str(s.get("name", "")).strip()
                    db_subs_by_catname[cname.strip().lower()][sname.lower()] = s

            sub_map = defaultdict(list)

            # Build canonical practical subcategories for each category in required order
            for cat_name, practical_sub_list in PRACTICAL_SUBCATEGORIES.items():
                cat_key = cat_name.strip().lower()
                cid = cat_name_to_id.get(cat_key, cat_key)
                canonical_items = []

                for sname in practical_sub_list:
                    s_lower = sname.strip().lower()
                    if s_lower in db_subs_by_catname[cat_key]:
                        rec = db_subs_by_catname[cat_key][s_lower]
                        sub_id = str(rec.get("id"))
                    else:
                        sub_id = f"sub_{cat_key}_{s_lower.replace(' ', '_').replace('/', '_')}"

                    item = {
                        "id": sub_id,
                        "name": sname,
                        "category_id": cid,
                        "default_priority": get_default_priority(cat_name, sname)
                    }
                    canonical_items.append(item)

                sub_map[cid] = canonical_items
                sub_map[cat_key] = canonical_items

            cls._categories = categories
            cls._locations = locations
            cls._subcategories_by_cat = dict(sub_map)

            return cls._categories, cls._subcategories_by_cat, cls._locations

    # -------------------------------------------------------------------------
    # SECURITY CODES CACHE
    # -------------------------------------------------------------------------
    @classmethod
    def get_security_code_record(cls, role: str, department_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        cache_key = f"{role}:{department_id or ''}"
        now = time.time()
        with cls._lock:
            cached = cls._security_codes_cache.get(cache_key)
            if cached and now < cached[0]:
                return cached[1]

        from database.supabase_client import get_trusted_backend_client
        client = get_trusted_backend_client()

        # Handle special roles
        from models.user import UserRole
        record = None

        if role == UserRole.LIBRARY_INCHARGE.value:
            lib_id = cls.get_special_dept_id("LIB")
            try:
                res = client.table("staff_security_codes").select("*").eq("role", "Library Incharge").execute()
                if res.data and len(res.data) > 0:
                    record = res.data[0]
                elif lib_id:
                    res = client.table("staff_security_codes").select("*").eq("role", "HOD").eq("department_id", lib_id).execute()
                    if res.data and len(res.data) > 0:
                        record = res.data[0]
            except Exception:
                pass

        elif role == UserRole.GENERAL_HOD.value:
            gen_id = cls.get_special_dept_id("GEN")
            try:
                res = client.table("staff_security_codes").select("*").eq("role", "General Department HOD").execute()
                if res.data and len(res.data) > 0:
                    record = res.data[0]
                elif gen_id:
                    res = client.table("staff_security_codes").select("*").eq("role", "HOD").eq("department_id", gen_id).execute()
                    if res.data and len(res.data) > 0:
                        record = res.data[0]
            except Exception:
                pass

        if record is None:
            try:
                query = client.table("staff_security_codes").select("*").eq("role", role)
                if department_id:
                    query = query.eq("department_id", department_id)
                res = query.execute()
                if res.data and len(res.data) > 0:
                    record = res.data[0]
            except Exception:
                pass

        with cls._lock:
            # Cache for 10 minutes (600s)
            cls._security_codes_cache[cache_key] = (now + 600, record)

        return record

    @classmethod
    def invalidate_security_codes(cls):
        with cls._lock:
            cls._security_codes_cache.clear()

    # -------------------------------------------------------------------------
    # SIGNED URL CACHE
    # -------------------------------------------------------------------------
    @classmethod
    def get_signed_url(cls, storage_path: str) -> Optional[str]:
        now = time.time()
        with cls._lock:
            entry = cls._signed_urls.get(storage_path)
            if entry and now < entry[0]:
                return entry[1]
        return None

    @classmethod
    def set_signed_url(cls, storage_path: str, signed_url: str, ttl_seconds: int = 3000):
        now = time.time()
        with cls._lock:
            cls._signed_urls[storage_path] = (now + ttl_seconds, signed_url)

    # -------------------------------------------------------------------------
    # METRICS CACHE
    # -------------------------------------------------------------------------
    @classmethod
    def get_cached_metrics(cls, role: str, department_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        key = (role, department_id)
        now = time.time()
        with cls._lock:
            entry = cls._metrics_cache.get(key)
            if entry and now < entry[0]:
                return entry[1]
        return None

    @classmethod
    def set_cached_metrics(cls, role: str, department_id: Optional[str], metrics: Dict[str, Any], ttl_seconds: int = 60):
        key = (role, department_id)
        now = time.time()
        with cls._lock:
            cls._metrics_cache[key] = (now + ttl_seconds, metrics)

    @classmethod
    def get_cached_dept_breakdown(cls) -> Optional[List[Dict[str, Any]]]:
        now = time.time()
        with cls._lock:
            if cls._dept_breakdown_cache and now < cls._dept_breakdown_cache[0]:
                return cls._dept_breakdown_cache[1]
        return None

    @classmethod
    def set_cached_dept_breakdown(cls, breakdown: List[Dict[str, Any]], ttl_seconds: int = 60):
        now = time.time()
        with cls._lock:
            cls._dept_breakdown_cache = (now + ttl_seconds, breakdown)

    @classmethod
    def invalidate_metrics(cls):
        with cls._lock:
            cls._metrics_cache.clear()
            cls._dept_breakdown_cache = None

    # -------------------------------------------------------------------------
    # NOTIFICATION UNREAD COUNT CACHE
    # -------------------------------------------------------------------------
    @classmethod
    def get_cached_unread_count(cls, user_id: str, role: str, department_id: Optional[str] = None) -> Optional[int]:
        key = (user_id, role, department_id)
        now = time.time()
        with cls._lock:
            entry = cls._unread_count_cache.get(key)
            if entry and now < entry[0]:
                return entry[1]
        return None

    @classmethod
    def set_cached_unread_count(cls, user_id: str, role: str, department_id: Optional[str], count: int, ttl_seconds: int = 30):
        key = (user_id, role, department_id)
        now = time.time()
        with cls._lock:
            cls._unread_count_cache[key] = (now + ttl_seconds, count)

    @classmethod
    def update_unread_count(cls, user_id: str, delta: int):
        with cls._lock:
            for k in list(cls._unread_count_cache.keys()):
                if k[0] == user_id:
                    exp, cnt = cls._unread_count_cache[k]
                    cls._unread_count_cache[k] = (exp, max(0, cnt + delta))

    @classmethod
    def clear_all(cls):
        with cls._lock:
            cls._departments = None
            cls._departments_by_code = None
            cls._departments_by_id = None
            cls._special_dept_ids.clear()
            cls._categories = None
            cls._locations = None
            cls._subcategories_by_cat = None
            cls._security_codes_cache.clear()
            cls._signed_urls.clear()
            cls._metrics_cache.clear()
            cls._dept_breakdown_cache = None
            cls._unread_count_cache.clear()
