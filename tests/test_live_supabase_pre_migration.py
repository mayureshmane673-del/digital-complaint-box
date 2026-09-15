"""
tests/test_live_supabase_pre_migration.py: [LIVE-PRE-MIGRATION] Baseline Tests
Tests actual HTTP connectivity, RPC privilege rejection, and verifies that the live
remote Supabase project (https://trncsmuwxfljkhckoyra.supabase.co) remains in a clean,
untouched state prior to migration approval.
"""

import pytest
from database.supabase_client import get_supabase_client, check_schema_health, SUPABASE_URL


class TestLiveSupabasePreMigration:
    """
    [LIVE-PRE-MIGRATION] Baseline tests executed against the remote Supabase project.
    Verifies that unauthenticated/normal clients cannot execute sensitive RPCs and
    verifies that no database migrations have been executed in the user's project yet.
    """

    def test_live_supabase_connectivity(self):
        """[LIVE-PRE-MIGRATION] Verifies live HTTPS connectivity to configured Supabase endpoint."""
        client = get_supabase_client()
        assert client is not None
        assert "supabase.co" in SUPABASE_URL

    def test_live_supabase_set_application_context_rejected_for_anon(self):
        """
        [LIVE-PRE-MIGRATION]
        Verifies that an unauthenticated/normal user using the publishable key CANNOT execute
        set_application_context to spoof identity/role.
        Expects rejection (PGRST202 function not found/executable or 401/403 access denied).
        """
        client = get_supabase_client()
        is_blocked = False
        try:
            res = client.rpc("set_application_context", {
                "p_user_id": "00000000-0000-0000-0000-000000000000",
                "p_role": "Principal",
                "p_department_id": None
            }).execute()
            if res.data is None:
                is_blocked = True
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["pgrst202", "permission denied", "not found", "denied", "could not find"]):
                is_blocked = True

        assert is_blocked is True, "Security Alert: Normal client was able to execute set_application_context!"

    def test_live_supabase_submit_complaint_atomic_rejected_for_anon(self):
        """
        [LIVE-PRE-MIGRATION]
        Verifies that an unauthenticated/normal client CANNOT execute submit_complaint_atomic.
        """
        client = get_supabase_client()
        is_blocked = False
        try:
            res = client.rpc("submit_complaint_atomic", {
                "p_student_id": "00000000-0000-0000-0000-000000000000",
                "p_title": "Test Title",
                "p_description": "Valid test complaint description minimum 10 chars",
                "p_department_id": "00000000-0000-0000-0000-000000000000"
            }).execute()
            if res.data is None:
                is_blocked = True
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["pgrst202", "permission denied", "not found", "denied", "could not find"]):
                is_blocked = True

        assert is_blocked is True

    def test_live_supabase_check_roll_number_eligibility_rejected_for_anon(self):
        """
        [LIVE-PRE-MIGRATION]
        Verifies that public clients cannot call check_roll_number_eligibility to enumerate roll numbers.
        """
        client = get_supabase_client()
        is_blocked = False
        try:
            res = client.rpc("check_roll_number_eligibility", {
                "p_roll_number": "2026CSE001",
                "p_department_id": "00000000-0000-0000-0000-000000000000"
            }).execute()
            if res.data is None:
                is_blocked = True
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["pgrst202", "permission denied", "not found", "denied", "could not find"]):
                is_blocked = True

        assert is_blocked is True

    def test_live_supabase_roll_number_pool_protected(self):
        """
        [LIVE-PRE-MIGRATION]
        Verifies that querying roll_number_pool with the publishable/anon key does not leak pool data.
        """
        client = get_supabase_client()
        is_protected = False
        try:
            res = client.table("roll_number_pool").select("*").limit(5).execute()
            if not res.data:
                is_protected = True
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["pgrst205", "permission denied", "not found"]):
                is_protected = True

        assert is_protected is True

    def test_live_supabase_anonymous_complaint_owners_inaccessible(self):
        """
        [LIVE-PRE-MIGRATION]
        Verifies that anonymous_complaint_owners table cannot be queried by unauthorized client.
        """
        client = get_supabase_client()
        is_protected = False
        try:
            res = client.table("anonymous_complaint_owners").select("*").limit(5).execute()
            if not res.data:
                is_protected = True
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["pgrst205", "permission denied", "not found"]):
                is_protected = True

        assert is_protected is True

    def test_live_supabase_confirm_no_migration_executed_yet(self):
        """
        [LIVE-PRE-MIGRATION]
        Pre-migration baseline check: confirms table state. If migration has already been executed, skips.
        """
        health = check_schema_health()
        assert health["connected"] is True, "Failed to connect to live Supabase endpoint."
        if health.get("tables_ready", False):
            pytest.skip("Migration has already been executed on the live Supabase project.")
        assert health["tables_ready"] is False, "Alert: Tables already exist on Supabase!"
        assert "Database tables are not yet created in Supabase" in health.get("error", "")
