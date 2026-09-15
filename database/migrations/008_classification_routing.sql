-- ============================================================================
-- Migration 008: Data Classification, Master Subcategories, and Role Routing
-- ============================================================================

-- 1. Schema Enhancements
-- ----------------------------------------------------------------------------
-- Add must_change_password column to students table
ALTER TABLE students 
ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;

-- Update role check constraint on staff_users to support all 6 roles
DO 
BEGIN
    ALTER TABLE staff_users DROP CONSTRAINT IF EXISTS staff_users_role_check;
    ALTER TABLE staff_users ADD CONSTRAINT staff_users_role_check 
        CHECK (role IN ('Principal', 'HOD', 'Coordinator', 'Hostel Incharge', 'Library Incharge', 'General Department HOD'));
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Constraint update for staff_users_role_check skipped or already applied.';
END ;

-- Update role check constraint on staff_security_codes to support all 6 roles
DO 
BEGIN
    ALTER TABLE staff_security_codes DROP CONSTRAINT IF EXISTS staff_security_codes_role_check;
    ALTER TABLE staff_security_codes ADD CONSTRAINT staff_security_codes_role_check 
        CHECK (role IN ('Principal', 'HOD', 'Coordinator', 'Hostel Incharge', 'Library Incharge', 'General Department HOD'));
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Constraint update for staff_security_codes_role_check skipped or already applied.';
END ;

-- 2. Special Institutional Departments
-- ----------------------------------------------------------------------------
INSERT INTO departments (code, name, is_active)
VALUES 
    ('GEN', 'General Department', TRUE),
    ('LIB', 'Library', TRUE)
ON CONFLICT (code) DO UPDATE SET is_active = TRUE;

-- 3. Initial Staff Security Codes for General HOD and Library Incharge
-- Default bcrypt hashes for initial security codes if not present
INSERT INTO staff_security_codes (role, department_id, code_hash, updated_by)
SELECT 
    'HOD', 
    id, 
    '',
    'system:migration_008'
FROM departments WHERE code IN ('GEN', 'LIB')
ON CONFLICT DO NOTHING;

-- 4. Composite Performance Indexes for Cross-Filtering and Duplicates
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_complaints_cat_subcat_prio 
    ON complaints (category_id, subcategory_id, priority);

CREATE INDEX IF NOT EXISTS idx_complaints_hostel_active 
    ON complaints (is_hostel, is_deleted) 
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_students_dept_year 
    ON students (department_id, year);

CREATE INDEX IF NOT EXISTS idx_complaints_dept_active 
    ON complaints (department_id, is_deleted) 
    WHERE is_deleted = FALSE;
