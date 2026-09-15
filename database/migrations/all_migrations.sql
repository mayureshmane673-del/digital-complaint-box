-- >>> FILE: 001_schema.sql >>>
-- ============================================================================
-- 001_schema.sql: Corrected Production Database Schema
-- Digital Complaint Box System
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Concurrency-safe complaint ID sequence starting at 101. Never reused.
CREATE SEQUENCE IF NOT EXISTS complaint_id_seq START WITH 101 INCREMENT BY 1;

-- 1. DEPARTMENTS (Exactly 5 Academic Engineering Departments)
CREATE TABLE IF NOT EXISTS departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. LOCATIONS (Managed by Principal)
CREATE TABLE IF NOT EXISTS locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. CATEGORIES & SUBCATEGORIES (Database-driven)
CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subcategories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(category_id, name)
);

-- 4. STAFF USERS
CREATE TABLE IF NOT EXISTS staff_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (role IN ('Principal', 'HOD', 'Coordinator', 'Hostel Incharge')),
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    password_hash VARCHAR(255) NOT NULL,
    security_question TEXT NOT NULL,
    security_answer_hash VARCHAR(255) NOT NULL,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Exactly one active HOD per academic department
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_hod_per_dept 
ON staff_users(department_id) 
WHERE role = 'HOD' AND is_active = TRUE;

-- Safe Staff Directory View (Omits password_hash and security_answer_hash)
CREATE OR REPLACE VIEW staff_directory AS
SELECT 
    id,
    username,
    full_name,
    role,
    department_id,
    is_locked,
    is_active,
    created_at,
    updated_at
FROM staff_users;

-- 5. STAFF SECURITY CODES / CONFIGURATION
CREATE TABLE IF NOT EXISTS staff_security_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role VARCHAR(30) NOT NULL CHECK (role IN ('Principal', 'HOD', 'Coordinator', 'Hostel Incharge')),
    department_id UUID REFERENCES departments(id) ON DELETE CASCADE,
    code_hash VARCHAR(255) NOT NULL,
    updated_by VARCHAR(100),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (role, department_id)
);

-- Safe Staff Security Code Info View (Omits code_hash)
CREATE OR REPLACE VIEW staff_security_code_info AS
SELECT 
    id,
    role,
    department_id,
    updated_by,
    updated_at
FROM staff_security_codes;

-- 6. ROLL NUMBER POOL (Managed only by Coordinators for their department)
CREATE TABLE IF NOT EXISTS roll_number_pool (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    roll_number VARCHAR(50) UNIQUE NOT NULL,
    added_by_coordinator_id UUID REFERENCES staff_users(id) ON DELETE SET NULL,
    is_registered BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. STUDENTS
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    roll_number VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    year VARCHAR(10) NOT NULL CHECK (year IN ('FE', 'SE', 'TE', 'BE', 'First Year', 'Second Year', 'Third Year', 'Final Year')),
    password_hash VARCHAR(255) NOT NULL,
    security_question TEXT NOT NULL,
    security_answer_hash VARCHAR(255) NOT NULL,
    is_hostel BOOLEAN NOT NULL DEFAULT FALSE,
    is_hostel_approved BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INT NOT NULL DEFAULT 0,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    locked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safe Student Directory View (Omits password_hash and security_answer_hash)
CREATE OR REPLACE VIEW student_directory AS
SELECT 
    id,
    roll_number,
    full_name,
    department_id,
    year,
    is_hostel,
    is_hostel_approved,
    is_locked,
    created_at
FROM students;

-- 8. HOSTEL REQUESTS
CREATE TABLE IF NOT EXISTS hostel_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    hostel_name VARCHAR(100) NOT NULL,
    block VARCHAR(50) NOT NULL,
    room_number VARCHAR(50) NOT NULL,
    request_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Approved', 'Denied')),
    deny_reason TEXT,
    reviewed_by UUID REFERENCES staff_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. ISSUE GROUPS
CREATE TABLE IF NOT EXISTS issue_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(200) NOT NULL,
    department_id UUID REFERENCES departments(id) ON DELETE CASCADE,
    is_hostel BOOLEAN NOT NULL DEFAULT FALSE,
    group_status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (group_status IN ('Pending', 'In Progress', 'Resolved')),
    primary_complaint_id INT,
    duplicate_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. COMPLAINTS
CREATE TABLE IF NOT EXISTS complaints (
    complaint_id INT PRIMARY KEY DEFAULT nextval('complaint_id_seq'),
    id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    -- For anonymous complaints, student_id is strictly NULL to prevent exposure
    student_id UUID REFERENCES students(id) ON DELETE SET NULL,
    is_anonymous BOOLEAN NOT NULL DEFAULT FALSE,
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    is_hostel BOOLEAN NOT NULL DEFAULT FALSE,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL CHECK (char_length(description) >= 10 AND char_length(description) <= 1000),
    category_id UUID REFERENCES categories(id) ON DELETE SET NULL,
    subcategory_id UUID REFERENCES subcategories(id) ON DELETE SET NULL,
    location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
    location_custom TEXT,
    category_custom TEXT,
    subcategory_custom TEXT,
    priority VARCHAR(20) NOT NULL DEFAULT 'Low' CHECK (priority IN ('Low', 'Medium', 'High', 'Urgent')),
    initial_priority VARCHAR(20) NOT NULL DEFAULT 'Low',
    auto_priority VARCHAR(20) NOT NULL DEFAULT 'Low',
    status VARCHAR(20) NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'In Progress', 'Resolved', 'Rejected')),
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by UUID REFERENCES staff_users(id) ON DELETE SET NULL,
    deleted_by_role VARCHAR(30),
    delete_reason TEXT,
    deleted_at TIMESTAMPTZ,
    issue_group_id UUID REFERENCES issue_groups(id) ON DELETE SET NULL,
    has_admin_action BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Foreign key linking issue_groups.primary_complaint_id back to complaints
ALTER TABLE issue_groups 
DROP CONSTRAINT IF EXISTS fk_primary_complaint;
ALTER TABLE issue_groups 
ADD CONSTRAINT fk_primary_complaint 
FOREIGN KEY (primary_complaint_id) REFERENCES complaints(complaint_id) ON DELETE SET NULL;

-- 11. ANONYMOUS COMPLAINT OWNERS (Strictly Private Table - Never Accessible by Staff)
CREATE TABLE IF NOT EXISTS anonymous_complaint_owners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id INT UNIQUE NOT NULL REFERENCES complaints(complaint_id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    ownership_token_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 12. COMPLAINT ATTACHMENTS (Max 2 per complaint, max 10MB each)
CREATE TABLE IF NOT EXISTS complaint_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id INT NOT NULL REFERENCES complaints(complaint_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size INT NOT NULL CHECK (file_size > 0 AND file_size <= 10485760),
    mime_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 13. COMPLAINT HISTORY (Immutable audit log)
CREATE TABLE IF NOT EXISTS complaint_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id INT NOT NULL REFERENCES complaints(complaint_id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    actor_type VARCHAR(20) NOT NULL CHECK (actor_type IN ('Student', 'Staff', 'System')),
    actor_role VARCHAR(30),
    actor_id VARCHAR(100),
    previous_state JSONB,
    new_state JSONB,
    remarks TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 14. COMPLAINT ASSIGNMENTS
CREATE TABLE IF NOT EXISTS complaint_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id INT NOT NULL REFERENCES complaints(complaint_id) ON DELETE CASCADE,
    assigned_to_type VARCHAR(20) NOT NULL CHECK (assigned_to_type IN ('team', 'person', 'custom')),
    assigned_to_name VARCHAR(150) NOT NULL,
    assigned_by UUID NOT NULL REFERENCES staff_users(id) ON DELETE CASCADE,
    assigned_by_role VARCHAR(30) NOT NULL,
    remarks TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 15. ISSUE GROUP MEMBERS (Prevent duplicate memberships)
CREATE TABLE IF NOT EXISTS issue_group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_group_id UUID NOT NULL REFERENCES issue_groups(id) ON DELETE CASCADE,
    complaint_id INT UNIQUE NOT NULL REFERENCES complaints(complaint_id) ON DELETE CASCADE,
    added_by UUID REFERENCES staff_users(id) ON DELETE SET NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 16. ISSUE GROUP HISTORY
CREATE TABLE IF NOT EXISTS issue_group_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_group_id UUID NOT NULL REFERENCES issue_groups(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    actor_id UUID REFERENCES staff_users(id) ON DELETE SET NULL,
    actor_role VARCHAR(30),
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 17. FEEDBACK (One feedback per student per complaint: UNIQUE(student_id, complaint_id), max 1 edit)
CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id INT NOT NULL REFERENCES complaints(complaint_id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    edit_count INT NOT NULL DEFAULT 0 CHECK (edit_count <= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id, complaint_id)
);

-- 18. NOTIFICATIONS (In-app only, 90-day retention)
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_type VARCHAR(20) NOT NULL CHECK (recipient_type IN ('student', 'staff', 'role')),
    recipient_id UUID,
    recipient_role VARCHAR(30),
    department_id UUID REFERENCES departments(id) ON DELETE CASCADE,
    title VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    reference_type VARCHAR(30) CHECK (reference_type IN ('complaint', 'issue_group', 'hostel_request', 'feedback')),
    reference_id VARCHAR(100),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 19. AUDIT LOGS
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    actor_id UUID,
    actor_role VARCHAR(30),
    ip_address VARCHAR(45),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- <<< END FILE: 001_schema.sql <<<

-- >>> FILE: 002_indexes.sql >>>
-- ============================================================================
-- 002_indexes.sql: Performance & Query Optimization Indexes
-- ============================================================================

-- Complaints indexes
CREATE INDEX IF NOT EXISTS idx_complaints_dept ON complaints(department_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_priority ON complaints(priority);
CREATE INDEX IF NOT EXISTS idx_complaints_created ON complaints(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_complaints_student ON complaints(student_id) WHERE student_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_complaints_is_anon ON complaints(is_anonymous);
CREATE INDEX IF NOT EXISTS idx_complaints_is_deleted ON complaints(is_deleted);
CREATE INDEX IF NOT EXISTS idx_complaints_is_hostel ON complaints(is_hostel);
CREATE INDEX IF NOT EXISTS idx_complaints_category ON complaints(category_id);
CREATE INDEX IF NOT EXISTS idx_complaints_subcategory ON complaints(subcategory_id);
CREATE INDEX IF NOT EXISTS idx_complaints_location ON complaints(location_id);
CREATE INDEX IF NOT EXISTS idx_complaints_issue_group ON complaints(issue_group_id);

-- Anonymous Complaint Owners (Strictly for student private tracking)
CREATE INDEX IF NOT EXISTS idx_anon_owners_student ON anonymous_complaint_owners(student_id);
CREATE INDEX IF NOT EXISTS idx_anon_owners_complaint ON anonymous_complaint_owners(complaint_id);

-- Complaint History indexes
CREATE INDEX IF NOT EXISTS idx_history_complaint_id ON complaint_history(complaint_id);
CREATE INDEX IF NOT EXISTS idx_history_created ON complaint_history(created_at DESC);

-- Complaint Attachments indexes
CREATE INDEX IF NOT EXISTS idx_attachments_complaint_id ON complaint_attachments(complaint_id);

-- Complaint Assignments indexes
CREATE INDEX IF NOT EXISTS idx_assignments_complaint_id ON complaint_assignments(complaint_id);
CREATE INDEX IF NOT EXISTS idx_assignments_active ON complaint_assignments(is_active);

-- Notifications indexes (optimized for badge count and 90-day retention cleanup)
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_role_dept ON notifications(recipient_role, department_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);

-- Feedback indexes
CREATE INDEX IF NOT EXISTS idx_feedback_student_complaint ON feedback(student_id, complaint_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);

-- Roll Number Pool indexes
CREATE INDEX IF NOT EXISTS idx_roll_pool_dept ON roll_number_pool(department_id, is_registered);
CREATE INDEX IF NOT EXISTS idx_roll_pool_number ON roll_number_pool(roll_number);

-- Students indexes
CREATE INDEX IF NOT EXISTS idx_students_roll ON students(roll_number);
CREATE INDEX IF NOT EXISTS idx_students_dept ON students(department_id);
CREATE INDEX IF NOT EXISTS idx_students_hostel ON students(is_hostel, is_hostel_approved);

-- Staff Users indexes
CREATE INDEX IF NOT EXISTS idx_staff_username ON staff_users(username);
CREATE INDEX IF NOT EXISTS idx_staff_role_dept ON staff_users(role, department_id);

-- Hostel Requests indexes
CREATE INDEX IF NOT EXISTS idx_hostel_requests_student ON hostel_requests(student_id);
CREATE INDEX IF NOT EXISTS idx_hostel_requests_status ON hostel_requests(status);
CREATE INDEX IF NOT EXISTS idx_hostel_requests_date ON hostel_requests(request_date DESC);

-- Issue Group indexes
CREATE INDEX IF NOT EXISTS idx_issue_groups_dept ON issue_groups(department_id, group_status);
CREATE INDEX IF NOT EXISTS idx_issue_groups_hostel ON issue_groups(is_hostel, group_status);
CREATE INDEX IF NOT EXISTS idx_issue_members_group ON issue_group_members(issue_group_id);
CREATE INDEX IF NOT EXISTS idx_issue_members_complaint ON issue_group_members(complaint_id);

-- <<< END FILE: 002_indexes.sql <<<

-- >>> FILE: 003_rls.sql >>>
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

-- <<< END FILE: 003_rls.sql <<<

-- >>> FILE: 004_storage.sql >>>
-- ============================================================================
-- 004_storage.sql: Private Storage Configuration & Scoped Access Policies
-- ============================================================================

-- Create private bucket for complaint attachments
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'complaint-attachments',
    'complaint-attachments',
    false, -- Strictly PRIVATE bucket
    10485760, -- 10MB limit
    ARRAY[
        'image/jpeg',
        'image/png',
        'image/webp',
        'video/mp4',
        'video/quicktime',
        'application/pdf'
    ]
)
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = 10485760,
    allowed_mime_types = ARRAY[
        'image/jpeg',
        'image/png',
        'image/webp',
        'video/mp4',
        'video/quicktime',
        'application/pdf'
    ];

-- Remove any old broad policies
DROP POLICY IF EXISTS "Authorized attachment access" ON storage.objects;
DROP POLICY IF EXISTS "Authorized attachment upload" ON storage.objects;
DROP POLICY IF EXISTS "Admin attachment delete" ON storage.objects;

-- ----------------------------------------------------------------------------
-- Scoped Storage SELECT Policy: Verified against complaint authorization
-- Object name format: 'complaints/<complaint_id>/<uuid>.<ext>'
-- ----------------------------------------------------------------------------
CREATE POLICY "Scoped complaint attachment read" ON storage.objects
FOR SELECT USING (
    bucket_id = 'complaint-attachments' AND (
        auth.role() = 'service_role' OR
        EXISTS (
            SELECT 1 FROM public.complaints c
            WHERE c.complaint_id::text = (storage.foldername(name))[2]
            AND (
                -- Student who owns complaint
                (c.student_id::text = current_setting('app.current_user_id', true) OR EXISTS (
                    SELECT 1 FROM public.anonymous_complaint_owners aco 
                    WHERE aco.complaint_id = c.complaint_id 
                    AND aco.student_id::text = current_setting('app.current_user_id', true)
                )) OR
                -- Principal
                current_setting('app.current_user_role', true) = 'Principal' OR
                EXISTS (SELECT 1 FROM public.staff_users su WHERE su.id::text = auth.uid()::text AND su.role = 'Principal') OR
                -- Hostel Incharge
                (c.is_hostel = true AND (
                    current_setting('app.current_user_role', true) = 'Hostel Incharge' OR
                    EXISTS (SELECT 1 FROM public.staff_users su WHERE su.id::text = auth.uid()::text AND su.role = 'Hostel Incharge')
                )) OR
                -- HOD & Coordinator
                (c.is_hostel = false AND (
                    (current_setting('app.current_user_role', true) IN ('HOD', 'Coordinator') AND current_setting('app.current_department_id', true) = c.department_id::text) OR
                    EXISTS (
                        SELECT 1 FROM public.staff_users su 
                        WHERE su.id::text = auth.uid()::text 
                        AND su.department_id = c.department_id 
                        AND su.role IN ('HOD', 'Coordinator')
                    )
                ))
            )
        )
    )
);

-- Scoped Upload Policy (Only associated student or backend service)
CREATE POLICY "Scoped complaint attachment upload" ON storage.objects
FOR INSERT WITH CHECK (
    bucket_id = 'complaint-attachments' AND (
        auth.role() = 'service_role' OR
        EXISTS (
            SELECT 1 FROM public.complaints c
            WHERE c.complaint_id::text = (storage.foldername(name))[2]
            AND (
                c.student_id::text = current_setting('app.current_user_id', true) OR
                EXISTS (
                    SELECT 1 FROM public.anonymous_complaint_owners aco 
                    WHERE aco.complaint_id = c.complaint_id 
                    AND aco.student_id::text = current_setting('app.current_user_id', true)
                ) OR
                c.student_id::text = auth.uid()::text
            )
        )
    )
);

-- Scoped Delete Policy (HOD, Hostel Incharge, Principal, or service role only)
CREATE POLICY "Scoped complaint attachment delete" ON storage.objects
FOR DELETE USING (
    bucket_id = 'complaint-attachments' AND (
        auth.role() = 'service_role' OR
        current_setting('app.current_user_role', true) IN ('Principal', 'HOD', 'Hostel Incharge') OR
        EXISTS (
            SELECT 1 FROM public.staff_users su 
            WHERE su.id::text = auth.uid()::text 
            AND su.role IN ('Principal', 'HOD', 'Hostel Incharge')
        )
    )
);

-- <<< END FILE: 004_storage.sql <<<

-- >>> FILE: 005_functions.sql >>>
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

-- <<< END FILE: 005_functions.sql <<<

-- >>> FILE: 006_seed.sql >>>
-- ============================================================================
-- 006_seed.sql: Seed Data for Departments, Categories, Locations, Codes
-- ============================================================================

-- 1. Academic Departments
INSERT INTO departments (code, name) VALUES
    ('CSE', 'Computer Science and Engineering'),
    ('AIDS', 'Artificial Intelligence and Data Science'),
    ('E&TC', 'Electronics and Telecommunication Engineering'),
    ('MECH', 'Mechanical Engineering'),
    ('Civil', 'Civil Engineering')
ON CONFLICT (code) DO NOTHING;

-- 2. Predefined Campus Locations (Managed by Principal)
INSERT INTO locations (name, is_active) VALUES
    ('Main Administrative Building', true),
    ('Computer Center / IT Block', true),
    ('Mechanical Workshop & Labs', true),
    ('Civil Engineering Block', true),
    ('E&TC Department Labs', true),
    ('Central Library & Reading Hall', true),
    ('Central Canteen & Cafeteria', true),
    ('Boys Hostel - Block A', true),
    ('Boys Hostel - Block B', true),
    ('Girls Hostel - Block A', true),
    ('Girls Hostel - Block B', true),
    ('College Auditorium', true),
    ('Sports Complex & Ground', true),
    ('Parking Area & Campus Gate', true)
ON CONFLICT (name) DO NOTHING;

-- 3. Categories & Subcategories
DO $$
DECLARE
    cat_id UUID;
BEGIN
    -- Cleaning & Hygiene
    INSERT INTO categories (name) VALUES ('Cleaning & Hygiene') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Classroom'), (cat_id, 'Lab'), (cat_id, 'Washroom'), 
            (cat_id, 'Canteen'), (cat_id, 'Campus'), (cat_id, 'Hostel')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Infrastructure
    INSERT INTO categories (name) VALUES ('Infrastructure') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Building'), (cat_id, 'Classroom'), (cat_id, 'Lab'), 
            (cat_id, 'Furniture'), (cat_id, 'Doors/Windows'), (cat_id, 'Fan')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Electricity
    INSERT INTO categories (name) VALUES ('Electricity') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Lights'), (cat_id, 'Fans'), (cat_id, 'Power Supply'), (cat_id, 'Switch/Socket')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Water & Sanitation
    INSERT INTO categories (name) VALUES ('Water & Sanitation') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Drinking Water'), (cat_id, 'Water Supply'), (cat_id, 'Leakage'), (cat_id, 'Drainage')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- IT & Computer
    INSERT INTO categories (name) VALUES ('IT & Computer') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Computer'), (cat_id, 'Internet/Wi-Fi'), (cat_id, 'Printer'), 
            (cat_id, 'Projector'), (cat_id, 'Software')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Academics
    INSERT INTO categories (name) VALUES ('Academics') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Timetable'), (cat_id, 'Exam'), (cat_id, 'Practical'), 
            (cat_id, 'Assignment'), (cat_id, 'Syllabus')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Faculty
    INSERT INTO categories (name) VALUES ('Faculty') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Teaching'), (cat_id, 'Attendance'), (cat_id, 'Behaviour'), (cat_id, 'Availability')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Canteen
    INSERT INTO categories (name) VALUES ('Canteen') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Food Quality'), (cat_id, 'Hygiene'), (cat_id, 'Pricing'), (cat_id, 'Service')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Hostel
    INSERT INTO categories (name) VALUES ('Hostel') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Room'), (cat_id, 'Washroom'), (cat_id, 'Food'), 
            (cat_id, 'Water'), (cat_id, 'Electricity'), (cat_id, 'Cleaning'), (cat_id, 'Security')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Transport
    INSERT INTO categories (name) VALUES ('Transport') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Bus'), (cat_id, 'Timing'), (cat_id, 'Route'), (cat_id, 'Driver/Service')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Student Related
    INSERT INTO categories (name) VALUES ('Student Related') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Misconduct'), (cat_id, 'Ragging/Harassment'), (cat_id, 'Lost & Found'), (cat_id, 'Other')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Security & Safety
    INSERT INTO categories (name) VALUES ('Security & Safety') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES 
            (cat_id, 'Security'), (cat_id, 'CCTV'), (cat_id, 'Emergency'), (cat_id, 'Unsafe Conditions')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;

    -- Other
    INSERT INTO categories (name) VALUES ('Other') ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id INTO cat_id;
    IF cat_id IS NOT NULL THEN
        INSERT INTO subcategories (category_id, name) VALUES (cat_id, 'General / Other')
        ON CONFLICT (category_id, name) DO NOTHING;
    END IF;
END $$;

-- 4. Initial Staff Security Codes
-- Pass@123 hashed via bcrypt
-- Role-appropriate codes:
-- - Principal
-- - Hostel Incharge
-- - HOD (per department)
-- - Coordinator (per department)
DO $$
DECLARE
    dept_rec RECORD;
    initial_hash VARCHAR(255) := '$2b$10$4sEh2FOELjApcp7UMZXx5usfHCYCLJwARlPP3UgI3BUVwd28NCpfK'; -- Pass@123
BEGIN
    -- Principal Security Code (No dept)
    INSERT INTO staff_security_codes (role, department_id, code_hash, updated_by)
    VALUES ('Principal', NULL, initial_hash, 'system_seed')
    ON CONFLICT DO NOTHING;

    -- Hostel Incharge Security Code (No dept)
    INSERT INTO staff_security_codes (role, department_id, code_hash, updated_by)
    VALUES ('Hostel Incharge', NULL, initial_hash, 'system_seed')
    ON CONFLICT DO NOTHING;

    -- Department HOD and Coordinator Codes
    FOR dept_rec IN SELECT id FROM departments LOOP
        -- HOD code
        INSERT INTO staff_security_codes (role, department_id, code_hash, updated_by)
        VALUES ('HOD', dept_rec.id, initial_hash, 'system_seed')
        ON CONFLICT DO NOTHING;

        -- Coordinator code (shared department coordinator code)
        INSERT INTO staff_security_codes (role, department_id, code_hash, updated_by)
        VALUES ('Coordinator', dept_rec.id, initial_hash, 'system_seed')
        ON CONFLICT DO NOTHING;
    END LOOP;
END $$;

-- <<< END FILE: 006_seed.sql <<<
