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
