-- ============================================================================
-- 005_functions.sql: Corrected Functions, Triggers, and Realtime Setup
-- Digital Complaint Box System
-- ============================================================================

-- 1. Timestamp updater function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- Apply updated_at triggers
DROP TRIGGER IF EXISTS trg_departments_updated_at ON departments;
CREATE TRIGGER trg_departments_updated_at
BEFORE UPDATE ON departments
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_staff_users_updated_at ON staff_users;
CREATE TRIGGER trg_staff_users_updated_at
BEFORE UPDATE ON staff_users
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_students_updated_at ON students;
CREATE TRIGGER trg_students_updated_at
BEFORE UPDATE ON students
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_complaints_updated_at ON complaints;
CREATE TRIGGER trg_complaints_updated_at
BEFORE UPDATE ON complaints
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_issue_groups_updated_at ON issue_groups;
CREATE TRIGGER trg_issue_groups_updated_at
BEFORE UPDATE ON issue_groups
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_hostel_requests_updated_at ON hostel_requests;
CREATE TRIGGER trg_hostel_requests_updated_at
BEFORE UPDATE ON hostel_requests
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_feedback_updated_at ON feedback;
CREATE TRIGGER trg_feedback_updated_at
BEFORE UPDATE ON feedback
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 2. 90-Day Notification Retention Cleanup (Does NOT touch complaint_history)
CREATE OR REPLACE FUNCTION cleanup_old_notifications()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM notifications
    WHERE created_at < NOW() - INTERVAL '90 days';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

REVOKE ALL ON FUNCTION cleanup_old_notifications() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION cleanup_old_notifications() TO service_role;

-- 3. Automatic Priority Escalation Calculator
CREATE OR REPLACE FUNCTION calculate_minimum_priority(dup_count INT, base_priority VARCHAR)
RETURNS VARCHAR
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    IF dup_count >= 6 THEN
        RETURN 'Urgent';
    ELSIF dup_count >= 4 THEN
        IF base_priority = 'Urgent' THEN
            RETURN 'Urgent';
        ELSE
            RETURN 'High';
        END IF;
    ELSIF dup_count >= 2 THEN
        IF base_priority IN ('Urgent', 'High') THEN
            RETURN base_priority;
        ELSE
            RETURN 'Medium';
        END IF;
    ELSE
        RETURN base_priority;
    END IF;
END;
$$;

-- 4. Secure Roll Number Eligibility Verification (SECURITY DEFINER with safe search_path)
-- Accessible exclusively to trusted backend service_role to prevent public enumeration.
CREATE OR REPLACE FUNCTION check_roll_number_eligibility(p_roll_number VARCHAR, p_department_id UUID)
RETURNS TABLE(is_eligible BOOLEAN, reason TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    rec RECORD;
BEGIN
    -- Strict safeguard: Only trusted backend/service_role can execute
    IF current_user != 'service_role' AND COALESCE(auth.role(), '') != 'service_role' THEN
        RAISE EXCEPTION 'Access denied. Only trusted backend service_role can execute check_roll_number_eligibility.';
    END IF;

    SELECT * INTO rec FROM roll_number_pool WHERE roll_number = UPPER(TRIM(p_roll_number));
    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'Roll Number is not present in the department pool. Please contact your Coordinator.'::TEXT;
        RETURN;
    END IF;

    IF rec.department_id != p_department_id THEN
        RETURN QUERY SELECT false, 'Roll Number belongs to a different academic department.'::TEXT;
        RETURN;
    END IF;

    IF rec.is_registered THEN
        RETURN QUERY SELECT false, 'Roll Number has already been registered.'::TEXT;
        RETURN;
    END IF;

    RETURN QUERY SELECT true, 'Roll number is valid and available for registration.'::TEXT;
END;
$$;

REVOKE ALL ON FUNCTION check_roll_number_eligibility(VARCHAR, UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION check_roll_number_eligibility(VARCHAR, UUID) TO service_role;

-- 5. Feedback Integrity Enforcement Triggers
CREATE OR REPLACE FUNCTION verify_feedback_eligibility()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    c_status VARCHAR;
    c_deleted BOOLEAN;
BEGIN
    SELECT status, is_deleted INTO c_status, c_deleted FROM complaints WHERE complaint_id = NEW.complaint_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Complaint #% does not exist.', NEW.complaint_id;
    END IF;
    IF c_deleted THEN
        RAISE EXCEPTION 'Cannot submit feedback on a deleted complaint.';
    END IF;
    IF c_status != 'Resolved' THEN
        RAISE EXCEPTION 'Feedback can only be submitted for Resolved complaints (current status: %).', c_status;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_verify_feedback ON feedback;
CREATE TRIGGER trg_verify_feedback
BEFORE INSERT ON feedback
FOR EACH ROW EXECUTE FUNCTION verify_feedback_eligibility();

CREATE OR REPLACE FUNCTION enforce_feedback_single_edit()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
BEGIN
    -- Disallow changing student_id or complaint_id
    IF NEW.student_id != OLD.student_id OR NEW.complaint_id != OLD.complaint_id THEN
        RAISE EXCEPTION 'Cannot transfer feedback to a different student or complaint.';
    END IF;

    -- Disallow editing if already edited once
    IF OLD.edit_count >= 1 THEN
        RAISE EXCEPTION 'Feedback can only be edited once. No further edits are permitted.';
    END IF;

    -- Disallow resetting or decrementing edit_count
    IF NEW.edit_count < OLD.edit_count THEN
        RAISE EXCEPTION 'Illegal operation: edit_count cannot be decremented or reset.';
    END IF;

    -- Enforce edit_count progression: exactly OLD.edit_count + 1 (transitions 0 -> 1)
    NEW.edit_count := OLD.edit_count + 1;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_feedback_single_edit ON feedback;
CREATE TRIGGER trg_enforce_feedback_single_edit
BEFORE UPDATE ON feedback
FOR EACH ROW EXECUTE FUNCTION enforce_feedback_single_edit();

-- 6. Session Context Setter for Backend Operations (Service-Role ONLY)
CREATE OR REPLACE FUNCTION set_application_context(
    p_user_id TEXT,
    p_role TEXT,
    p_department_id TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    -- Strict safeguard: Only service_role can call this function
    IF current_user != 'service_role' AND COALESCE(auth.role(), '') != 'service_role' THEN
        RAISE EXCEPTION 'Access denied. Only service_role can set application context.';
    END IF;

    PERFORM set_config('app.current_user_id', p_user_id, false);
    PERFORM set_config('app.current_user_role', p_role, false);
    IF p_department_id IS NOT NULL THEN
        PERFORM set_config('app.current_department_id', p_department_id, false);
    ELSE
        PERFORM set_config('app.current_department_id', '', false);
    END IF;
END;
$$;

REVOKE ALL ON FUNCTION set_application_context(TEXT, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION set_application_context(TEXT, TEXT, TEXT) TO service_role;

-- 7. Atomic Complaint Submission Function (SECURITY DEFINER with safe search_path)
-- Accessible EXCLUSIVELY to trusted backend service_role.
-- Validates student enrollment, department match, and hostel residency from trusted DB state.
CREATE OR REPLACE FUNCTION submit_complaint_atomic(
    p_student_id UUID,
    p_title VARCHAR(200),
    p_description TEXT,
    p_department_id UUID,
    p_category_id UUID DEFAULT NULL,
    p_subcategory_id UUID DEFAULT NULL,
    p_location_id UUID DEFAULT NULL,
    p_location_custom TEXT DEFAULT NULL,
    p_category_custom TEXT DEFAULT NULL,
    p_subcategory_custom TEXT DEFAULT NULL,
    p_priority VARCHAR(20) DEFAULT 'Low',
    p_is_anonymous BOOLEAN DEFAULT FALSE,
    p_is_hostel BOOLEAN DEFAULT FALSE,
    p_ownership_token_hash VARCHAR(255) DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_complaint_id INT;
    v_new_complaint complaints%ROWTYPE;
    v_student students%ROWTYPE;
    v_actual_student_id UUID;
    v_clean_title TEXT;
    v_clean_desc TEXT;
BEGIN
    -- 1. Strict safeguard: Only trusted backend/service_role can execute
    IF current_user != 'service_role' AND COALESCE(auth.role(), '') != 'service_role' THEN
        RAISE EXCEPTION 'Access denied. Only trusted backend service_role can execute submit_complaint_atomic.';
    END IF;

    -- 2. Verify student session context if application context is set
    IF current_app_user_id() IS NOT NULL AND current_app_user_id() != '' THEN
        IF p_student_id::text != current_app_user_id() THEN
            RAISE EXCEPTION 'Impersonation rejected: p_student_id (%) does not match current session identity (%).',
                p_student_id, current_app_user_id();
        END IF;
    END IF;

    -- 3. Verify that p_student_id exists in students table and is active/valid
    IF p_student_id IS NULL THEN
        RAISE EXCEPTION 'A valid student_id is required.';
    END IF;

    SELECT * INTO v_student FROM students WHERE id = p_student_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Student record not found or invalid student_id.';
    END IF;

    IF v_student.is_locked THEN
        RAISE EXCEPTION 'Student account is locked. Complaints cannot be submitted.';
    END IF;

    -- 4. Department Isolation Verification:
    -- Caller-supplied p_department_id MUST match student's enrolled department!
    -- Student CANNOT submit complaints to another academic department.
    IF p_department_id != v_student.department_id THEN
        RAISE EXCEPTION 'Department mismatch: Student is registered under department % but attempted to submit for %.', 
            v_student.department_id, p_department_id;
    END IF;

    -- 5. Hostel Eligibility Verification:
    -- If p_is_hostel is requested, student MUST have is_hostel_approved = true in database!
    -- Caller cannot bypass hostel approval by simply toggling p_is_hostel = true.
    IF p_is_hostel THEN
        IF NOT v_student.is_hostel OR NOT v_student.is_hostel_approved THEN
            RAISE EXCEPTION 'Hostel complaint rejected: Student does not have an approved hostel residency status.';
        END IF;
    END IF;

    -- 6. Validate description length (10 to 1000 chars)
    v_clean_desc := TRIM(p_description);
    IF char_length(v_clean_desc) < 10 OR char_length(v_clean_desc) > 1000 THEN
        RAISE EXCEPTION 'Description must be between 10 and 1000 characters.';
    END IF;

    -- 7. Validate title (3 to 200 chars)
    v_clean_title := TRIM(p_title);
    IF char_length(v_clean_title) < 3 OR char_length(v_clean_title) > 200 THEN
        RAISE EXCEPTION 'Title must be between 3 and 200 characters.';
    END IF;

    -- 8. Validate location requirement: either location_id or location_custom
    IF p_location_id IS NULL AND (p_location_custom IS NULL OR TRIM(p_location_custom) = '') THEN
        RAISE EXCEPTION 'Location is compulsory (select a location or specify Other).';
    END IF;

    -- 9. Anonymous handling: student_id in complaints table is strictly NULL
    -- Token is mandatory for anonymous ownership mapping
    IF p_is_anonymous THEN
        v_actual_student_id := NULL;
        IF p_ownership_token_hash IS NULL OR TRIM(p_ownership_token_hash) = '' THEN
            RAISE EXCEPTION 'Ownership token hash is required for anonymous complaint submission.';
        END IF;
    ELSE
        v_actual_student_id := p_student_id;
    END IF;

    -- 10. Insert into complaints table
    INSERT INTO complaints (
        student_id,
        is_anonymous,
        department_id,
        is_hostel,
        title,
        description,
        category_id,
        subcategory_id,
        location_id,
        location_custom,
        category_custom,
        subcategory_custom,
        priority,
        initial_priority,
        auto_priority,
        status,
        is_deleted,
        has_admin_action
    ) VALUES (
        v_actual_student_id,
        p_is_anonymous,
        v_student.department_id,
        p_is_hostel,
        v_clean_title,
        v_clean_desc,
        p_category_id,
        p_subcategory_id,
        p_location_id,
        NULLIF(TRIM(p_location_custom), ''),
        NULLIF(TRIM(p_category_custom), ''),
        NULLIF(TRIM(p_subcategory_custom), ''),
        p_priority,
        p_priority,
        p_priority,
        'Pending',
        false,
        false
    )
    RETURNING * INTO v_new_complaint;

    v_complaint_id := v_new_complaint.complaint_id;

    -- 11. If anonymous, insert into anonymous_complaint_owners in the SAME transaction
    IF p_is_anonymous THEN
        INSERT INTO anonymous_complaint_owners (
            complaint_id,
            student_id,
            ownership_token_hash
        ) VALUES (
            v_complaint_id,
            p_student_id,
            p_ownership_token_hash
        );
    END IF;

    -- 12. Insert initial complaint history
    INSERT INTO complaint_history (
        complaint_id,
        action,
        actor_type,
        actor_role,
        actor_id,
        new_state,
        remarks
    ) VALUES (
        v_complaint_id,
        'SUBMITTED',
        'Student',
        'Student',
        CASE WHEN p_is_anonymous THEN 'Anonymous' ELSE p_student_id::TEXT END,
        jsonb_build_object('status', 'Pending', 'priority', p_priority),
        'Complaint registered.'
    );

    -- 13. Create staff notifications
    IF p_is_hostel THEN
        INSERT INTO notifications (
            recipient_type,
            recipient_role,
            title,
            message,
            reference_type,
            reference_id
        ) VALUES (
            'role',
            'Hostel Incharge',
            'New Hostel Complaint #' || v_complaint_id,
            'A new complaint was submitted: ' || SUBSTRING(v_clean_title, 1, 50),
            'complaint',
            v_complaint_id::TEXT
        );
    ELSE
        INSERT INTO notifications (
            recipient_type,
            recipient_role,
            department_id,
            title,
            message,
            reference_type,
            reference_id
        ) VALUES (
            'role',
            'HOD',
            v_student.department_id,
            'New Dept Complaint #' || v_complaint_id,
            'A new complaint was submitted: ' || SUBSTRING(v_clean_title, 1, 50),
            'complaint',
            v_complaint_id::TEXT
        );

        INSERT INTO notifications (
            recipient_type,
            recipient_role,
            department_id,
            title,
            message,
            reference_type,
            reference_id
        ) VALUES (
            'role',
            'Coordinator',
            v_student.department_id,
            'New Dept Complaint #' || v_complaint_id,
            'A new complaint was submitted: ' || SUBSTRING(v_clean_title, 1, 50),
            'complaint',
            v_complaint_id::TEXT
        );
    END IF;

    -- Return the complaint record as JSONB
    RETURN to_jsonb(v_new_complaint);
END;
$$;

REVOKE ALL ON FUNCTION submit_complaint_atomic(
    UUID, VARCHAR, TEXT, UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, VARCHAR, BOOLEAN, BOOLEAN, VARCHAR
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION submit_complaint_atomic(
    UUID, VARCHAR, TEXT, UUID, UUID, UUID, UUID, TEXT, TEXT, TEXT, VARCHAR, BOOLEAN, BOOLEAN, VARCHAR
) TO service_role;

-- 8. Student Record Protected-Field Update Trigger
-- Enforces that students cannot modify protected fields directly:
-- department_id, roll_number, is_hostel_approved, is_locked, failed_login_attempts, locked_at, password_hash, security_answer_hash
CREATE OR REPLACE FUNCTION enforce_student_update_restrictions()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    -- Intercept updates initiated from student context or non-service_role callers
    IF (current_user != 'service_role' AND COALESCE(auth.role(), '') != 'service_role')
       OR current_app_role() = 'Student' THEN
        IF NEW.department_id IS DISTINCT FROM OLD.department_id THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot modify department_id.';
        END IF;
        IF NEW.roll_number IS DISTINCT FROM OLD.roll_number THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot modify roll_number.';
        END IF;
        IF NEW.is_hostel_approved IS DISTINCT FROM OLD.is_hostel_approved THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot self-approve hostel residency status.';
        END IF;
        IF NEW.is_locked IS DISTINCT FROM OLD.is_locked THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot modify account lock status.';
        END IF;
        IF NEW.failed_login_attempts IS DISTINCT FROM OLD.failed_login_attempts THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot reset failed_login_attempts directly.';
        END IF;
        IF NEW.locked_at IS DISTINCT FROM OLD.locked_at THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot modify locked_at timestamp.';
        END IF;
        IF NEW.password_hash IS DISTINCT FROM OLD.password_hash THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot modify password_hash directly; use password reset flow.';
        END IF;
        IF NEW.security_answer_hash IS DISTINCT FROM OLD.security_answer_hash THEN
            RAISE EXCEPTION 'Unauthorized: Students cannot modify security_answer_hash directly.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_student_update_restrictions ON students;
CREATE TRIGGER trg_enforce_student_update_restrictions
BEFORE UPDATE ON students
FOR EACH ROW
EXECUTE FUNCTION enforce_student_update_restrictions();

-- 9. Realtime Publication Configuration
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE complaints, notifications, hostel_requests, issue_groups;
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;
