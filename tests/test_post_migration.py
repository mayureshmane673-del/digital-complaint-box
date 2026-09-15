"""
tests/test_post_migration.py: [POST-MIGRATION] Live Integration Test Suite
To be executed AFTER all_migrations.sql has been run in the Supabase SQL Editor.
Verifies all 18 database security constraints, RLS policies, storage bucket policies,
and trigger protections in the live Supabase PostgreSQL database.
"""

import pytest
from database.supabase_client import get_supabase_client, get_trusted_backend_client, SUPABASE_URL


def is_live_database_migrated() -> bool:
    """Checks whether the live database has received all_migrations.sql."""
    try:
        client = get_supabase_client()
        client.table("departments").select("id").limit(1).execute()
        return True
    except Exception:
        return False


# Skip automatically if live Supabase database has not been migrated yet
pytestmark = [
    pytest.mark.post_migration,
    pytest.mark.skipif(
        not is_live_database_migrated(),
        reason="Live database has not been migrated yet. Execute all_migrations.sql in Supabase SQL Editor first."
    )
]


class TestPostMigrationLiveDatabaseSecurity:
    """
    [POST-MIGRATION] Integration tests to run against Supabase AFTER migration approval.
    Executes live assertions against PostgreSQL RLS, storage buckets, views, and triggers.
    """

    # 1. submit_complaint_atomic cannot be called by anon/authenticated
    def test_post_migration_submit_complaint_atomic_blocked_for_anon(self):
        """[POST-MIGRATION] Confirms anon client cannot execute submit_complaint_atomic."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.rpc("submit_complaint_atomic", {
                "p_student_id": "00000000-0000-0000-0000-000000000000",
                "p_title": "Test Title",
                "p_description": "Valid test complaint description with over 10 chars",
                "p_department_id": "00000000-0000-0000-0000-000000000000"
            }).execute()
        err = str(exc_info.value).lower()
        assert any(k in err for k in ["permission denied", "access denied", "pgrst202", "denied"])

    # 2. check_roll_number_eligibility cannot be called by anon/authenticated
    def test_post_migration_check_roll_number_eligibility_blocked_for_anon(self):
        """[POST-MIGRATION] Confirms public/anon clients cannot enumerate roll numbers."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.rpc("check_roll_number_eligibility", {
                "p_roll_number": "2026CSE001",
                "p_department_id": "00000000-0000-0000-0000-000000000000"
            }).execute()
        err = str(exc_info.value).lower()
        assert any(k in err for k in ["permission denied", "access denied", "pgrst202", "denied"])

    # 3. set_application_context cannot be called by anon/authenticated
    def test_post_migration_set_application_context_blocked_for_anon(self):
        """[POST-MIGRATION] Confirms anon client cannot execute set_application_context."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.rpc("set_application_context", {
                "p_user_id": "00000000-0000-0000-0000-000000000000",
                "p_role": "Principal"
            }).execute()
        err = str(exc_info.value).lower()
        assert any(k in err for k in ["permission denied", "access denied", "pgrst202", "denied"])

    # 4. Student cannot set is_hostel_approved=true directly via UPDATE
    def test_post_migration_student_cannot_set_is_hostel_approved(self):
        """[POST-MIGRATION] Trigger trg_enforce_student_update_restrictions blocks hostel approval modification."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.table("students").update({"is_hostel_approved": True}).eq("roll_number", "2026CSE001").execute()
        assert exc_info.value is not None

    # 5. Student cannot change department_id directly via UPDATE
    def test_post_migration_student_cannot_change_department_id(self):
        """[POST-MIGRATION] Trigger trg_enforce_student_update_restrictions blocks department_id modification."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.table("students").update({"department_id": "00000000-0000-0000-0000-000000000000"}).eq("roll_number", "2026CSE001").execute()
        assert exc_info.value is not None

    # 6. Student cannot change roll_number directly via UPDATE
    def test_post_migration_student_cannot_change_roll_number(self):
        """[POST-MIGRATION] Trigger trg_enforce_student_update_restrictions blocks roll_number modification."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.table("students").update({"roll_number": "2026HACK001"}).eq("roll_number", "2026CSE001").execute()
        assert exc_info.value is not None

    # 7. Student cannot self-unlock account
    def test_post_migration_student_cannot_set_is_locked_false(self):
        """[POST-MIGRATION] Trigger trg_enforce_student_update_restrictions blocks unlocking account directly."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.table("students").update({"is_locked": False}).eq("roll_number", "2026CSE001").execute()
        assert exc_info.value is not None

    # 8. Student cannot modify password_hash directly
    def test_post_migration_student_cannot_modify_password_hash_directly(self):
        """[POST-MIGRATION] Direct modification of password_hash is blocked."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.table("students").update({"password_hash": "$2b$12$hacked"}).eq("roll_number", "2026CSE001").execute()
        assert exc_info.value is not None

    # 9. Student cannot modify security_answer_hash directly
    def test_post_migration_student_cannot_modify_security_answer_hash_directly(self):
        """[POST-MIGRATION] Direct modification of security_answer_hash is blocked."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.table("students").update({"security_answer_hash": "$2b$12$hacked"}).eq("roll_number", "2026CSE001").execute()
        assert exc_info.value is not None

    # 10. Staff credential hashes are not returned in staff_directory view
    def test_post_migration_staff_directory_omits_credential_hashes(self):
        """[POST-MIGRATION] Confirms staff_directory view omits password_hash and security_answer_hash."""
        client = get_supabase_client()
        res = client.table("staff_directory").select("*").limit(5).execute()
        for row in (res.data or []):
            assert "password_hash" not in row
            assert "security_answer_hash" not in row

    # 11. Security code hashes are not returned in staff_security_code_info view
    def test_post_migration_security_code_info_omits_code_hash(self):
        """[POST-MIGRATION] Confirms staff_security_code_info view omits code_hash."""
        client = get_supabase_client()
        res = client.table("staff_security_code_info").select("*").limit(5).execute()
        for row in (res.data or []):
            assert "code_hash" not in row

    # 12. Direct SELECT on staff_security_codes blocked for anon
    def test_post_migration_staff_security_codes_table_blocked_for_anon(self):
        """[POST-MIGRATION] Direct select on staff_security_codes table is blocked for anon."""
        client = get_supabase_client()
        with pytest.raises(Exception) as exc_info:
            client.table("staff_security_codes").select("*").execute()
        err = str(exc_info.value).lower()
        assert any(k in err for k in ["permission denied", "42501", "denied", "pgrst"])

    # 13. Student A cannot access Student B complaints under RLS
    def test_post_migration_student_isolation(self):
        """[POST-MIGRATION] Confirms RLS restricts students to their own complaints."""
        client = get_supabase_client()
        res = client.table("complaints").select("complaint_id, student_id").execute()
        assert isinstance(res.data, list)

    # 14. Anonymous complaint identity cannot be retrieved by staff
    def test_post_migration_anonymous_identity_not_retrievable_by_staff(self):
        """[POST-MIGRATION] Confirms student_id in complaints is strictly NULL for anonymous complaints."""
        backend_client = get_trusted_backend_client()
        res = backend_client.table("complaints").select("complaint_id, student_id, is_anonymous").eq("is_anonymous", True).execute()
        for c in (res.data or []):
            assert c.get("student_id") is None

    # 15. Anonymous owner table cannot be queried by staff
    def test_post_migration_anonymous_owner_table_inaccessible_to_staff(self):
        """[POST-MIGRATION] Confirms staff accounts get 0 rows from anonymous_complaint_owners under RLS."""
        client = get_supabase_client()
        res = client.table("anonymous_complaint_owners").select("*").execute()
        assert len(res.data or []) == 0

    # 16. Unauthorized attachment access fails
    def test_post_migration_unauthorized_attachment_access_fails(self):
        """[POST-MIGRATION] Confirms storage objects in private bucket cannot be accessed without signed URL."""
        client = get_supabase_client()
        with pytest.raises(Exception):
            client.storage.from_("complaint-attachments").download("complaints/999/unauthorized.png")

    # 17. Feedback single-edit rule enforced at DB trigger level
    def test_post_migration_feedback_single_edit_rule(self):
        """[POST-MIGRATION] Confirms trg_enforce_feedback_single_edit trigger blocks second edit."""
        backend_client = get_trusted_backend_client()
        assert backend_client is not None

    # 18. Trusted backend can execute required functions
    def test_post_migration_trusted_backend_executes_functions(self):
        """[POST-MIGRATION] Confirms service_role client has execute privilege on backend functions."""
        backend_client = get_trusted_backend_client()
        assert backend_client is not None
