-- =============================================================================
-- Migration 007: Account Management, Soft-Deletion Lifecycle & Partial Active Index
-- PREPARED LOCALLY - DO NOT EXECUTE WITHOUT EXPLICIT USER APPROVAL
-- =============================================================================

-- 1. Add deactivation tracking columns to students
ALTER TABLE students 
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS deactivated_by UUID,
ADD COLUMN IF NOT EXISTS deactivation_reason TEXT;

-- 2. Add deactivation tracking columns to staff_users
ALTER TABLE staff_users 
ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS deactivated_by UUID,
ADD COLUMN IF NOT EXISTS deactivation_reason TEXT;

-- 3. Upgrade staff_users username uniqueness to active accounts only
-- Allows deactivated staff usernames to be safely reused by new staff accounts
-- without destructive deletion of historical accounts or breaking FK links.
ALTER TABLE staff_users DROP CONSTRAINT IF EXISTS staff_users_username_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_staff_users_active_username 
ON staff_users(username) 
WHERE is_active = TRUE;

-- 4. Audit Log index on actor and event type for rapid account history lookups
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor 
ON audit_logs(actor_id, event_type);
