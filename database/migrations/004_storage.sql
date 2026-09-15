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
