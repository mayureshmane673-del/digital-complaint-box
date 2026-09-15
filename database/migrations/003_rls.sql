-- ============================================================================
-- 003_rls.sql: Corrected Row Level Security (RLS) Policies
-- Digital Complaint Box System
-- ============================================================================

-- Enable RLS on all operational tables
ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE subcategories ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_security_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE roll_number_pool ENABLE ROW LEVEL SECURITY;
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE hostel_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaints ENABLE ROW LEVEL SECURITY;
ALTER TABLE anonymous_complaint_owners ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaint_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaint_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE complaint_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_group_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- HELPER FUNCTIONS FOR APP & AUTH IDENTITY (RECURSION-FREE)
-- Compatible with both Supabase Auth JWT and backend session context settings
-- Uses SECURITY DEFINER with fixed search_path to prevent infinite RLS recursion
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION current_app_user_id() RETURNS TEXT
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    IF auth.uid() IS NOT NULL THEN
        RETURN auth.uid()::text;
    END IF;
    RETURN current_setting('app.current_user_id', true);
END;
$$;

CREATE OR REPLACE FUNCTION current_app_role() RETURNS TEXT
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    RETURN current_setting('app.current_user_role', true);
END;
$$;

CREATE OR REPLACE FUNCTION current_app_dept_id() RETURNS TEXT
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
BEGIN
    RETURN current_setting('app.current_department_id', true);
END;
$$;

-- SECURITY DEFINER helper to evaluate Principal role without evaluating staff_users RLS
CREATE OR REPLACE FUNCTION is_app_principal() RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF current_app_role() = 'Principal' THEN
        RETURN true;
    END IF;
    RETURN EXISTS (
        SELECT 1 FROM staff_users 
        WHERE id::text = current_app_user_id() AND role = 'Principal'
    );
END;
$$;

-- SECURITY DEFINER helper to query staff role without evaluating staff_users RLS
CREATE OR REPLACE FUNCTION get_staff_role(p_user_id TEXT) RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT role FROM staff_users WHERE id::text = p_user_id LIMIT 1;
$$;

-- SECURITY DEFINER helper to query staff department without evaluating staff_users RLS
CREATE OR REPLACE FUNCTION get_staff_department(p_user_id TEXT) RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT department_id FROM staff_users WHERE id::text = p_user_id LIMIT 1;
$$;

-- ----------------------------------------------------------------------------
-- 1. REFERENCE DATA (Public read for active items)
-- ----------------------------------------------------------------------------
CREATE POLICY "Public read departments" ON departments FOR SELECT USING (true);
CREATE POLICY "Public read active locations" ON locations FOR SELECT USING (is_active = true);
CREATE POLICY "Principal manage locations" ON locations FOR ALL USING (
    auth.role() = 'service_role' OR
    current_app_role() = 'Principal' OR
    is_app_principal()
);

CREATE POLICY "Public read active categories" ON categories FOR SELECT USING (is_active = true);
CREATE POLICY "Public read active subcategories" ON subcategories FOR SELECT USING (is_active = true);

-- ----------------------------------------------------------------------------
-- 2. ROLL NUMBER POOL (Coordinator-Exclusive for their Own Department)
-- NO "OR true". Students and other roles CANNOT read the pool.
-- ----------------------------------------------------------------------------
CREATE POLICY "Coordinator view own dept roll numbers" ON roll_number_pool
FOR SELECT USING (
    auth.role() = 'service_role' OR
    (
        current_app_role() = 'Coordinator' AND 
        current_app_dept_id()::text = roll_number_pool.department_id::text
    ) OR
    (
        get_staff_role(current_app_user_id()) = 'Coordinator' AND 
        get_staff_department(current_app_user_id()) = roll_number_pool.department_id
    )
);

CREATE POLICY "Coordinator insert own dept roll numbers" ON roll_number_pool
FOR INSERT WITH CHECK (
    auth.role() = 'service_role' OR
    (
        current_app_role() = 'Coordinator' AND 
        current_app_dept_id()::text = roll_number_pool.department_id::text
    ) OR
    (
        get_staff_role(current_app_user_id()) = 'Coordinator' AND 
        get_staff_department(current_app_user_id()) = roll_number_pool.department_id
    )
);

CREATE POLICY "Coordinator update own dept roll numbers" ON roll_number_pool
FOR UPDATE USING (
    auth.role() = 'service_role' OR
    (
        current_app_role() = 'Coordinator' AND 
        current_app_dept_id()::text = roll_number_pool.department_id::text
    ) OR
    (
        get_staff_role(current_app_user_id()) = 'Coordinator' AND 
        get_staff_department(current_app_user_id()) = roll_number_pool.department_id
    )
);

-- ----------------------------------------------------------------------------
-- 3. STAFF USERS & SECURITY CODES
-- Recursion-free policies. Credential hashes masked from normal clients.
-- staff_security_codes is restricted to service_role; metadata read via staff_security_code_info.
-- ----------------------------------------------------------------------------
CREATE POLICY "Staff read own profile or principal read all" ON staff_users
FOR SELECT USING (
    auth.role() = 'service_role' OR 
    current_app_user_id() = id::text OR 
    current_app_role() = 'Principal' OR
    is_app_principal()
);

CREATE POLICY "Staff update own profile or principal update all" ON staff_users
FOR UPDATE USING (
    auth.role() = 'service_role' OR 
    current_app_user_id() = id::text OR 
    current_app_role() = 'Principal' OR
    is_app_principal()
);

-- Security codes table is restricted to trusted backend service_role only
-- HOD/Coordinator/Hostel Incharge/Principal cannot read code_hash via direct SELECT
CREATE POLICY "Security codes service_role only" ON staff_security_codes
FOR ALL USING (auth.role() = 'service_role');

-- ----------------------------------------------------------------------------
-- 4. STUDENTS (Protected against unauthorized modification)
-- Column updates protected via trigger trg_enforce_student_update_restrictions
-- ----------------------------------------------------------------------------
CREATE POLICY "Students read own record" ON students
FOR SELECT USING (
    auth.role() = 'service_role' OR
    current_app_user_id() = id::text OR
    current_app_role() = 'Principal' OR
    is_app_principal() OR
    (current_app_role() IN ('HOD', 'Coordinator') AND current_app_dept_id() = department_id::text) OR
    (
        get_staff_role(current_app_user_id()) IN ('HOD', 'Coordinator') AND 
        get_staff_department(current_app_user_id()) = students.department_id
    )
);

CREATE POLICY "Students update own record" ON students
FOR UPDATE USING (
    auth.role() = 'service_role' OR 
    (current_app_user_id() = id::text AND current_app_role() = 'Student')
);

-- ----------------------------------------------------------------------------
-- 5. HOSTEL REQUESTS (Strict: Student, Hostel Incharge, Principal ONLY)
-- Department HOD and Coordinator CANNOT access hostel requests.
-- ----------------------------------------------------------------------------
CREATE POLICY "Hostel requests access" ON hostel_requests
FOR ALL USING (
    auth.role() = 'service_role' OR
    current_app_user_id() = student_id::text OR
    current_app_role() IN ('Hostel Incharge', 'Principal') OR
    is_app_principal() OR
    (get_staff_role(current_app_user_id()) = 'Hostel Incharge')
);

-- ----------------------------------------------------------------------------
-- 6. ANONYMOUS COMPLAINT OWNERS (Strictly Private - Staff CANNOT query)
-- ----------------------------------------------------------------------------
CREATE POLICY "Student access own anonymous ownership" ON anonymous_complaint_owners
FOR ALL USING (
    auth.role() = 'service_role' OR
    current_app_user_id() = student_id::text
);

-- ----------------------------------------------------------------------------
-- 7. COMPLAINTS (Department Isolation & Anonymous Identity Concealment)
-- ----------------------------------------------------------------------------
CREATE POLICY "Complaints select policy" ON complaints
FOR SELECT USING (
    auth.role() = 'service_role' OR
    -- Student view: own non-anonymous complaint OR anonymous complaint owned in private table
    (
        current_app_user_id() = student_id::text OR
        EXISTS (
            SELECT 1 FROM anonymous_complaint_owners aco 
            WHERE aco.complaint_id = complaints.complaint_id 
            AND aco.student_id::text = current_app_user_id()
        )
    ) OR
    -- Principal: all non-deleted complaints across campus
    current_app_role() = 'Principal' OR
    is_app_principal() OR
    -- Hostel Incharge: hostel complaints only
    (
        is_hostel = true AND (
            current_app_role() = 'Hostel Incharge' OR
            get_staff_role(current_app_user_id()) = 'Hostel Incharge'
        )
    ) OR
    -- HOD & Coordinator: own department non-hostel complaints only
    (
        is_hostel = false AND (
            (current_app_role() IN ('HOD', 'Coordinator') AND current_app_dept_id() = complaints.department_id::text) OR
            (
                get_staff_role(current_app_user_id()) IN ('HOD', 'Coordinator') AND 
                get_staff_department(current_app_user_id()) = complaints.department_id
            )
        )
    )
);

CREATE POLICY "Complaints insert policy" ON complaints
FOR INSERT WITH CHECK (
    auth.role() = 'service_role' OR
    current_app_user_id() = student_id::text OR
    (is_anonymous = true AND student_id IS NULL)
);

CREATE POLICY "Complaints update policy" ON complaints
FOR UPDATE USING (
    auth.role() = 'service_role' OR
    -- Student: can edit only within 10 mins and if no admin action
    (
        (current_app_user_id() = student_id::text OR EXISTS (
            SELECT 1 FROM anonymous_complaint_owners aco 
            WHERE aco.complaint_id = complaints.complaint_id 
            AND aco.student_id::text = current_app_user_id()
        )) AND 
        has_admin_action = false AND 
        created_at >= NOW() - INTERVAL '10 minutes'
    ) OR
    -- Principal: system-wide
    current_app_role() = 'Principal' OR
    is_app_principal() OR
    -- Hostel Incharge: hostel complaints only
    (
        is_hostel = true AND (
            current_app_role() = 'Hostel Incharge' OR
            get_staff_role(current_app_user_id()) = 'Hostel Incharge'
        )
    ) OR
    -- HOD & Coordinator: own department non-hostel complaints only
    (
        is_hostel = false AND (
            (current_app_role() IN ('HOD', 'Coordinator') AND current_app_dept_id() = complaints.department_id::text) OR
            (
                get_staff_role(current_app_user_id()) IN ('HOD', 'Coordinator') AND 
                get_staff_department(current_app_user_id()) = complaints.department_id
            )
        )
    )
);

-- ----------------------------------------------------------------------------
-- 8. COMPLAINT ATTACHMENTS (Scoped strictly to associated complaint)
-- ----------------------------------------------------------------------------
CREATE POLICY "Complaint attachments select policy" ON complaint_attachments
FOR SELECT USING (
    auth.role() = 'service_role' OR
    EXISTS (
        SELECT 1 FROM complaints c 
        WHERE c.complaint_id = complaint_attachments.complaint_id
        AND (
            -- Student who owns complaint
            (c.student_id::text = current_app_user_id() OR EXISTS (
                SELECT 1 FROM anonymous_complaint_owners aco 
                WHERE aco.complaint_id = c.complaint_id 
                AND aco.student_id::text = current_app_user_id()
            )) OR
            -- Principal
            current_app_role() = 'Principal' OR
            is_app_principal() OR
            -- Hostel Incharge
            (c.is_hostel = true AND (
                current_app_role() = 'Hostel Incharge' OR
                get_staff_role(current_app_user_id()) = 'Hostel Incharge'
            )) OR
            -- HOD & Coordinator
            (c.is_hostel = false AND (
                (current_app_role() IN ('HOD', 'Coordinator') AND current_app_dept_id() = c.department_id::text) OR
                (
                    get_staff_role(current_app_user_id()) IN ('HOD', 'Coordinator') AND 
                    get_staff_department(current_app_user_id()) = c.department_id
                )
            ))
        )
    )
);

CREATE POLICY "Complaint attachments insert policy" ON complaint_attachments
FOR INSERT WITH CHECK (
    auth.role() = 'service_role' OR
    EXISTS (
        SELECT 1 FROM complaints c 
        WHERE c.complaint_id = complaint_attachments.complaint_id
        AND (
            c.student_id::text = current_app_user_id() OR
            EXISTS (
                SELECT 1 FROM anonymous_complaint_owners aco 
                WHERE aco.complaint_id = c.complaint_id 
                AND aco.student_id::text = current_app_user_id()
            )
        )
    )
);

-- ----------------------------------------------------------------------------
-- 9. ISSUE GROUPS (Department/Hostel Scoped Access)
-- ----------------------------------------------------------------------------
CREATE POLICY "Issue groups scoped select policy" ON issue_groups
FOR SELECT USING (
    auth.role() = 'service_role' OR
    -- Principal: all groups
    current_app_role() = 'Principal' OR
    is_app_principal() OR
    -- Hostel Incharge: hostel groups only
    (
        is_hostel = true AND (
            current_app_role() = 'Hostel Incharge' OR
            get_staff_role(current_app_user_id()) = 'Hostel Incharge'
        )
    ) OR
    -- HOD & Coordinator: own department non-hostel groups only
    (
        is_hostel = false AND (
            (current_app_role() IN ('HOD', 'Coordinator') AND current_app_dept_id() = issue_groups.department_id::text) OR
            (
                get_staff_role(current_app_user_id()) IN ('HOD', 'Coordinator') AND 
                get_staff_department(current_app_user_id()) = issue_groups.department_id
            )
        )
    ) OR
    -- Student: only groups containing complaints they submitted
    EXISTS (
        SELECT 1 FROM issue_group_members igm
        JOIN complaints c ON c.complaint_id = igm.complaint_id
        WHERE igm.issue_group_id = issue_groups.id
        AND (
            c.student_id::text = current_app_user_id() OR
            EXISTS (
                SELECT 1 FROM anonymous_complaint_owners aco 
                WHERE aco.complaint_id = c.complaint_id 
                AND aco.student_id::text = current_app_user_id()
            )
        )
    )
);

CREATE POLICY "Issue groups staff manage policy" ON issue_groups
FOR ALL USING (
    auth.role() = 'service_role' OR
    current_app_role() = 'Principal' OR
    is_app_principal() OR
    (is_hostel = true AND (current_app_role() = 'Hostel Incharge' OR get_staff_role(current_app_user_id()) = 'Hostel Incharge')) OR
    (
        is_hostel = false AND (
            (current_app_role() IN ('HOD', 'Coordinator') AND current_app_dept_id() = issue_groups.department_id::text) OR
            (
                get_staff_role(current_app_user_id()) IN ('HOD', 'Coordinator') AND 
                get_staff_department(current_app_user_id()) = issue_groups.department_id
            )
        )
    )
);

-- Issue Group Members
CREATE POLICY "Issue group members access" ON issue_group_members
FOR ALL USING (
    auth.role() = 'service_role' OR
    EXISTS (
        SELECT 1 FROM issue_groups ig 
        WHERE ig.id = issue_group_members.issue_group_id
        AND (
            current_app_role() = 'Principal' OR
            is_app_principal() OR
            (ig.is_hostel = true AND (current_app_role() = 'Hostel Incharge' OR get_staff_role(current_app_user_id()) = 'Hostel Incharge')) OR
            (
                ig.is_hostel = false AND (
                    (current_app_role() IN ('HOD', 'Coordinator') AND current_app_dept_id() = ig.department_id::text) OR
                    (
                        get_staff_role(current_app_user_id()) IN ('HOD', 'Coordinator') AND 
                        get_staff_department(current_app_user_id()) = ig.department_id
                    )
                )
            )
        )
    )
);

-- ----------------------------------------------------------------------------
-- 10. FEEDBACK (Resolved complaints only, UNIQUE(student_id, complaint_id))
-- ----------------------------------------------------------------------------
CREATE POLICY "Feedback select policy" ON feedback
FOR SELECT USING (
    auth.role() = 'service_role' OR
    current_app_user_id() = student_id::text OR
    current_app_role() = 'Principal' OR
    is_app_principal() OR
    EXISTS (
        SELECT 1 FROM complaints c 
        WHERE c.complaint_id = feedback.complaint_id
        AND (
            (c.is_hostel = true AND (current_app_role() = 'Hostel Incharge' OR get_staff_role(current_app_user_id()) = 'Hostel Incharge')) OR
            (
                c.is_hostel = false AND (
                    current_app_dept_id() = c.department_id::text OR
                    get_staff_department(current_app_user_id()) = c.department_id
                )
            )
        )
    )
);

CREATE POLICY "Feedback student insert" ON feedback
FOR INSERT WITH CHECK (
    (auth.role() = 'service_role' OR current_app_user_id() = student_id::text) AND
    EXISTS (
        SELECT 1 FROM complaints c 
        WHERE c.complaint_id = feedback.complaint_id 
        AND c.status = 'Resolved' 
        AND c.is_deleted = false
    )
);

CREATE POLICY "Feedback student update once" ON feedback
FOR UPDATE USING (
    (auth.role() = 'service_role' OR current_app_user_id() = student_id::text) AND 
    edit_count < 1
);

-- ----------------------------------------------------------------------------
-- 11. NOTIFICATIONS
-- ----------------------------------------------------------------------------
CREATE POLICY "Notifications access policy" ON notifications
FOR ALL USING (
    auth.role() = 'service_role' OR
    current_app_user_id() = recipient_id::text OR
    (
        recipient_type = 'role' AND 
        (
            current_app_role() = recipient_role OR
            get_staff_role(current_app_user_id()) = notifications.recipient_role
        ) AND 
        (notifications.department_id IS NULL OR notifications.department_id::text = current_app_dept_id())
    )
);

-- ----------------------------------------------------------------------------
-- 12. COMPLAINT HISTORY & ASSIGNMENTS
-- ----------------------------------------------------------------------------
CREATE POLICY "Complaint history select" ON complaint_history
FOR SELECT USING (
    auth.role() = 'service_role' OR
    EXISTS (
        SELECT 1 FROM complaints c 
        WHERE c.complaint_id = complaint_history.complaint_id
        AND (
            c.student_id::text = current_app_user_id() OR
            EXISTS (
                SELECT 1 FROM anonymous_complaint_owners aco 
                WHERE aco.complaint_id = c.complaint_id 
                AND aco.student_id::text = current_app_user_id()
            ) OR
            current_app_role() = 'Principal' OR
            is_app_principal() OR
            (c.is_hostel = true AND (current_app_role() = 'Hostel Incharge' OR get_staff_role(current_app_user_id()) = 'Hostel Incharge')) OR
            (
                c.is_hostel = false AND (
                    current_app_dept_id() = c.department_id::text OR
                    get_staff_department(current_app_user_id()) = c.department_id
                )
            )
        )
    )
);

CREATE POLICY "Complaint assignments select" ON complaint_assignments
FOR SELECT USING (
    auth.role() = 'service_role' OR
    EXISTS (
        SELECT 1 FROM complaints c 
        WHERE c.complaint_id = complaint_assignments.complaint_id
        AND (
            current_app_role() = 'Principal' OR
            is_app_principal() OR
            (c.is_hostel = true AND (current_app_role() = 'Hostel Incharge' OR get_staff_role(current_app_user_id()) = 'Hostel Incharge')) OR
            (
                c.is_hostel = false AND (
                    current_app_dept_id() = c.department_id::text OR
                    get_staff_department(current_app_user_id()) = c.department_id
                )
            )
        )
    )
);

-- ----------------------------------------------------------------------------
-- 13. CREDENTIAL HASH EXPOSURE RESTRICTIONS & COLUMN-LEVEL SECURITY
-- ----------------------------------------------------------------------------
-- Revoke raw security codes table access from normal clients; service_role only
REVOKE ALL ON staff_security_codes FROM PUBLIC, anon, authenticated;
GRANT ALL ON staff_security_codes TO service_role;
GRANT SELECT ON staff_security_code_info TO authenticated, service_role;

-- Revoke staff password_hash and security_answer_hash from normal clients
REVOKE SELECT ON staff_users FROM PUBLIC, anon, authenticated;
GRANT SELECT (id, username, full_name, role, department_id, is_locked, is_active, created_at, updated_at) ON staff_users TO authenticated;
GRANT ALL ON staff_users TO service_role;
GRANT SELECT ON staff_directory TO authenticated, service_role;

-- Revoke student password_hash and security_answer_hash from normal clients
REVOKE SELECT ON students FROM PUBLIC, anon, authenticated;
GRANT SELECT (id, roll_number, full_name, department_id, year, is_hostel, is_hostel_approved, is_locked, failed_login_attempts, locked_at, created_at, updated_at) ON students TO authenticated;
GRANT ALL ON students TO service_role;
GRANT SELECT ON student_directory TO authenticated, service_role;
