# Digital Complaint Box System

An enterprise-grade, privacy-preserving, multi-role campus grievance redressal and institutional transparency system built with **Python**, **Flet**, **Supabase PostgreSQL**, **Supabase Storage**, and **Supabase Realtime**.

---

## 1. Project Overview

The Digital Complaint Box System modernizes traditional physical and console-based complaint systems into a modern desktop and mobile-friendly application. It enforces strict academic hierarchy, department boundaries, non-destructive duplicate grouping, automatic priority escalation, anonymous complaint identity protection, and full audit traceability.

### Core Capabilities:
- **Academic Departments**: Exactly 5 academic engineering departments: `CSE`, `AIDS`, `E&TC`, `MECH`, `Civil`.
- **Role Hierarchy**:
  - **Principal**: Highest authority, campus-wide view, soft deletion, administrative reset of all staff security codes, location management. (Cannot manually alter complaint priority).
  - **HOD**: Exactly one active HOD per academic department. Full complaint lifecycle management (assign, soft delete, update status, remarks, priority, issue groups). Can change own HOD security code and department Coordinator code.
  - **Coordinator**: Multiple per department. Can view/manage department complaints, change status, priority, and issue groups. **Exclusively manages the Roll Number Pool** (manual addition + batch Excel import). *Cannot delete or assign complaints; cannot modify security codes.*
  - **Hostel Incharge**: Special authority with no academic department. Manages hostel requests (Approve/Deny with compulsory reason), hostel complaints, assignment, soft delete, priority, and hostel issue groups.
  - **Student**: Registers using pre-authorized Roll Number from Coordinator pool. Submits grievances (public or fully anonymous). Can edit within 10 minutes (unless admin action occurred). Rates resolution (1-5 stars, maximum 1 edit). Cannot delete complaints.
- **Privacy-Preserving Anonymous Mode**: Cryptographic token mechanism allows students to track their anonymous complaints in "My Complaints", while completely concealing identity, student ID, and roll number from HOD, Coordinator, Hostel Incharge, and Principal.
- **Local Duplicate Detection & Issue Groups (+N)**: Hybrid NLP algorithm (exact department/category/location match + token Jaccard + suffix stemming + n-grams) groups duplicates without destructive merging or deleting. Automatic priority minimum escalates from Low/Medium to High (at 4) and Urgent (at 6+).
- **Private Supabase Storage**: Max 2 attachments per complaint (JPG, PNG, WEBP, MP4, MOV, PDF up to 10MB) stored in private bucket with time-limited signed URLs.
- **In-App Notification Center**: 90-day retention notifications with badge counter and real-time alerts.

---

## 2. Technology Stack

- **Frontend**: Python, Flet (Responsive Material 3 desktop & mobile layout)
- **Backend**: Python Service Layer (`services/`, `models/`, `utils/`)
- **Primary Database**: Supabase PostgreSQL
- **File Storage**: Supabase Storage (Bucket: `complaint-attachments`)
- **Realtime**: Supabase Realtime WebSocket engine
- **Security & Cryptography**: Bcrypt with SHA-256 HMAC peppering
- **Data Import**: OpenPyXL, Pandas

---

## 3. Directory Structure

```
D:\complent box\
├── app.py                         # Application main entry point
├── requirements.txt               # Production Python dependencies
├── .env                           # Active environment configuration
├── .env.example                   # Template environment configuration
├── .gitignore                     # Git exclusion rules
├── README.md                      # Complete system documentation
├── database/
│   ├── migrations/
│   │   ├── 001_schema.sql         # 18 normalized tables, sequences (start 101), constraints
│   │   ├── 002_indexes.sql        # Performance indexes (status, priority, depts, dates)
│   │   ├── 003_rls.sql            # Supabase Row Level Security policies
│   │   ├── 004_storage.sql        # Storage bucket configuration & policies
│   │   ├── 005_functions.sql      # Triggers, auto-priority, 90-day cleaner, realtime
│   │   ├── 006_seed.sql           # Departments, categories, locations, Pass@123 hashes
│   │   └── all_migrations.sql     # Consolidated SQL file for Supabase SQL Editor
│   ├── supabase_client.py         # Resilient Supabase client with auth session & query builders
│   └── migration_runner.py        # Migration verification and automation tool
├── models/
│   ├── user.py                    # Student, StaffUser, StaffSecurityCode, RollNumberEntry
│   ├── complaint.py               # Complaint, Attachment, ComplaintHistory, Assignment
│   ├── issue_group.py             # IssueGroup, IssueGroupMember, IssueGroupHistory
│   ├── hostel.py                  # HostelRequest, HostelRequestStatus
│   ├── feedback.py                # Feedback (1-5 rating, max 1 edit)
│   └── notification.py            # Notification (90-day retention)
├── services/
│   ├── auth_service.py            # Login, registration, 5-attempt lockout, recovery
│   ├── security_code_service.py   # Staff security code rules (HOD/Coordinator/Principal)
│   ├── roll_number_service.py     # Coordinator pool, Excel (.xlsx/.xls) batch import
│   ├── complaint_service.py       # Submission, 10m edit lock, soft delete, transitions
│   ├── duplicate_service.py       # Modular local NLP similarity, auto-priority escalation
│   ├── issue_group_service.py     # Grouping (+N), independent status preservation
│   ├── hostel_service.py          # Hostel request lifecycle (Pending, Approved, Denied)
│   ├── storage_service.py         # File validation, private uploads, signed URLs
│   ├── feedback_service.py        # Resolved-only feedback, single edit constraint
│   ├── notification_service.py    # In-app dispatch, badge counts, 90-day retention cleaner
│   └── analytics_service.py       # Department comparison, resolution duration metrics
├── ui/
│   ├── theme.py                   # Material 3 color system and typography
│   ├── state.py                   # User session context and view routers
│   ├── components/
│   │   ├── navbar.py              # Role-aware navigation rail and top app bar
│   │   ├── stat_card.py           # Metric summary cards
│   │   ├── complaint_card.py      # Complaint card with badges, chips, +N indicator
│   │   ├── complaint_detail.py    # Detailed modal (timeline, attachments, action form)
│   │   ├── notification_drawer.py # Realtime notification center
│   │   └── excel_importer.py      # Roll number Excel import dialog with summary chips
│   └── views/
│       ├── auth_view.py           # Student & Staff tabs, login, registration, recovery
│       ├── student_view.py        # Dashboard, New Complaint wizard, My Complaints, Feedback
│       ├── staff_view.py          # Dynamic dashboard for HOD, Coordinator, Hostel, Principal
│       └── analytics_view.py      # Cross-department comparative analytics
├── utils/
│   ├── security.py                # Bcrypt password hashing, answer normalization, tokens
│   ├── validators.py              # Password policy, 10-1000 char description, file validator
│   └── helpers.py                 # Formatting, status colors, priority colors
└── tests/
    ├── test_auth.py               # Auth, password policy, 5-attempt lockout, recovery
    ├── test_complaints.py         # 10-minute edit lock, admin action lock, soft delete
    ├── test_duplicates.py         # Local text similarity, auto-priority escalation
    ├── test_feedback.py           # Resolved-only feedback, 1-edit constraint
    ├── test_roles.py              # Coordinator, HOD, Principal, Hostel Incharge boundaries
    ├── test_roll_numbers.py       # Pool format validation, Coordinator authority
    └── test_storage.py            # File format and size limits (max 10MB)
```

---

## 4. Setup & Installation

### Step 1: Clone or Navigate to Project
```powershell
cd "D:\complent box"
```

### Step 2: Set Up Virtual Environment (Optional but Recommended)
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Verify `.env` has the provided Supabase project credentials:
```ini
SUPABASE_URL=https://trncsmuwxfljkhckoyra.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_beZbQfSIK54uypoJ18WnNw_XqgobOnQ

# Optional: Supabase Service Role Key (Loaded ONLY on secure server/backend operations)
SUPABASE_SERVICE_ROLE_KEY=

# Optional: Direct PostgreSQL connection string for automated migrations
DATABASE_URL=

# App Security Settings
APP_SECRET_KEY=college-complaint-box-production-secure-key-2026
MAX_FAILED_LOGIN_ATTEMPTS=5
STORAGE_BUCKET=complaint-attachments
```

---

## 5. Supabase Database & Storage Setup

### Executing Migrations in Supabase:
1. Open your Supabase Dashboard:
   `https://supabase.com/dashboard/project/trncsmuwxfljkhckoyra`
2. In the left navigation sidebar, click on **SQL Editor**.
3. Click **New Query**.
4. Open the consolidated file on your disk:
   `D:\complent box\database\migrations\all_migrations.sql`
5. Copy its entire content, paste it into the Supabase SQL Editor, and click **RUN**.
6. The script will automatically:
   - Create all 18 normalized tables with foreign keys and unique constraints
   - Initialize the `complaint_id_seq` starting at 101
   - Configure Row Level Security (RLS) policies
   - Create performance indexes
   - Configure the `complaint-attachments` storage bucket
   - Seed all 5 academic departments (`CSE`, `AIDS`, `E&TC`, `MECH`, `Civil`), campus locations, categories, subcategories, and initial staff security codes.

### Verifying Schema Health:
Run the migration check tool:
```powershell
python database/migration_runner.py
```

---

## 6. How to Run the Application

Start the desktop and mobile-responsive Flet application:
```powershell
python app.py
```

---

## 7. How to Run Automated Tests

Execute the full suite of automated unit and security tests:
```powershell
pytest -v
```

All 23 test suites will run, verifying:
- Password policy and 5-attempt account lockout
- Student 10-minute edit window and immediate admin action lock
- Soft deletion rules with compulsory reason
- Local text similarity and automatic priority escalation (Urgent at 6+)
- Feedback 1-to-5 star rating and single edit constraint
- Coordinator, HOD, and Principal permission boundaries
- Roll number pool department isolation
- Attachment file type and 10MB size limits

---

## 8. Initial Staff Security Codes & Default Credentials

For initial testing and setup, staff security codes have been pre-seeded into the database using secure bcrypt hashing for:

- **Initial Staff Security Code**: `Pass@123`

### Security Code Rules:
- **HOD**: Can update own HOD code and the shared Coordinator code for their department.
- **Coordinator**: Cannot modify any security codes.
- **Hostel Incharge**: Can update own code (requires previous code or security question).
- **Principal**: Can administratively reset any HOD, Coordinator, or Hostel Incharge security code directly.
- **Passwords**: No user can view another user's password; only secure password reset with security questions is allowed.
