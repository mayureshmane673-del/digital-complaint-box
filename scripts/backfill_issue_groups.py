"""
scripts/backfill_issue_groups.py: Safe one-time backfill script for classroom cleaning complaints.
Targets strictly complaints #111, #112, and #113 (explicit IDs only).
Uses IssueGroupService with the trusted backend client so history, duplicate count,
and auto-priority escalation remain completely consistent.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import logging
from database.supabase_client import get_trusted_backend_client
from services.issue_group_service import IssueGroupService
from services.cache_service import CacheService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_issue_groups")

TARGET_COMPLAINT_IDS = [111, 112, 113]


def run_backfill():
    client = get_trusted_backend_client()

    print("=" * 70)
    print("BACKFILL DRY/LIVE RUN: COMPLAINTS #111, #112, #113")
    print("=" * 70)

    # 1. BEFORE STATE
    print("\n--- [STATE BEFORE BACKFILL] ---")
    c_res = client.table("complaints").select(
        "complaint_id, title, department_id, category_id, subcategory_id, is_hostel, priority, issue_group_id, created_at"
    ).in_("complaint_id", TARGET_COMPLAINT_IDS).order("complaint_id", desc=False).execute()

    existing_complaints = {c["complaint_id"]: c for c in (c_res.data or [])}
    if len(existing_complaints) != len(TARGET_COMPLAINT_IDS):
        print(f"ERROR: Expected complaints {TARGET_COMPLAINT_IDS}, found only {list(existing_complaints.keys())}.")
        sys.exit(1)

    for cid in TARGET_COMPLAINT_IDS:
        c = existing_complaints[cid]
        print(f"Complaint #{cid}: title='{c.get('title')}', issue_group_id={c.get('issue_group_id')}, priority='{c.get('priority')}'")

    # Check if any is already in a group
    already_grouped = [cid for cid, c in existing_complaints.items() if c.get("issue_group_id")]
    if already_grouped:
        print(f"WARNING: Complaints already grouped: {already_grouped}. Aborting to avoid double-grouping.")
        sys.exit(1)

    # 2. EXECUTE BACKFILL
    print("\n--- [EXECUTING BACKFILL VIA IssueGroupService] ---")
    primary_id = 111
    target_group_id = None

    for dup_id in [112, 113]:
        print(f"Linking complaint #{dup_id} to primary #{primary_id}...")
        ok, msg, grp_id = IssueGroupService.create_or_link_issue_group(
            primary_complaint_id=primary_id,
            duplicate_complaint_id=dup_id,
            actor_role="System"
        )
        if not ok or not grp_id:
            print(f"FATAL ERROR while linking #{dup_id}: {msg}. ABORTING.")
            sys.exit(1)
        print(f" -> Success: {msg} (Group ID: {grp_id})")
        target_group_id = grp_id

    # Invalidate cache
    CacheService.invalidate_issue_groups()
    CacheService.invalidate_metrics()

    # 3. AFTER STATE
    print("\n--- [STATE AFTER BACKFILL] ---")
    # Query issue_groups
    g_res = client.table("issue_groups").select("*").eq("id", target_group_id).execute()
    created_group = g_res.data[0] if g_res.data else {}
    print(f"Issue Group: {json.dumps(created_group, indent=2, default=str)}")

    # Query issue_group_members
    m_res = client.table("issue_group_members").select("*").eq("issue_group_id", target_group_id).order("complaint_id", desc=False).execute()
    print(f"Members ({len(m_res.data or [])} total):")
    for m in (m_res.data or []):
        print(f" - Member: complaint_id={m.get('complaint_id')}, issue_group_id={m.get('issue_group_id')}, added_by={m.get('added_by')}")

    # Query complaints
    c_after = client.table("complaints").select(
        "complaint_id, title, priority, auto_priority, issue_group_id"
    ).in_("complaint_id", TARGET_COMPLAINT_IDS).order("complaint_id", desc=False).execute()
    print("Complaints updated state:")
    for c in (c_after.data or []):
        print(f" - Complaint #{c.get('complaint_id')}: issue_group_id={c.get('issue_group_id')}, priority={c.get('priority')}, auto_priority={c.get('auto_priority')}")

    # Query issue_group_history
    h_res = client.table("issue_group_history").select("*").eq("issue_group_id", target_group_id).order("created_at", desc=False).execute()
    print(f"Group History Entries ({len(h_res.data or [])} total):")
    for h in (h_res.data or []):
        print(f" - Action: {h.get('action')}, Actor: {h.get('actor_role')}, Details: {h.get('details')}, At: {h.get('created_at')}")

    print("\nBackfill successfully completed!")


if __name__ == "__main__":
    run_backfill()
