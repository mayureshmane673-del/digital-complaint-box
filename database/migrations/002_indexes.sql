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
