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
