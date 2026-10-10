-- ============================================================================
-- Migration 009 (Phase 1): Add must_change_password flag & sync legacy reset records
-- PREPARED LOCALLY - DO NOT EXECUTE AUTOMATICALLY OR AGAINST PRODUCTION WITHOUT EXPLICIT APPROVAL
-- Non-destructive, additive, and 100% backward-compatible with running production application.
-- ============================================================================

-- 1. Add must_change_password column to students table (safe, non-destructive, backwards-compatible)
ALTER TABLE public.students
ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Performance index for rapid lookup of accounts requiring mandatory credential change
CREATE INDEX IF NOT EXISTS idx_students_must_change_password
ON public.students (id)
WHERE must_change_password = TRUE;

-- 3. Data backfill: Synchronize the must_change_password flag for legacy reset records.
-- NOTE: In Phase 1, the RESET_REQUIRED: prefix on security_question is deliberately PRESERVED
-- to maintain full backward-compatibility with the currently running application.
-- Neither security_question nor security_answer_hash are modified by this statement.
-- Idempotent: once must_change_password = TRUE, subsequent runs match 0 rows.
UPDATE public.students
SET must_change_password = TRUE
WHERE LEFT(security_question, 15) = 'RESET_REQUIRED:'
  AND must_change_password = FALSE;
