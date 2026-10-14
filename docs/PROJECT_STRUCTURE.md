# FUNDAMICS LMS Backend — Project Structure

This document provides a comprehensive, verified map of the actual repository layout, detailing the responsibilities, dependencies, and component relationships of every file and folder.

---

## 1. Verified Directory Tree

```text
d:\fundamics_backend/
├── .dockerignore                     # Files excluded from Docker builds
├── .env.example                      # Environment variables template with safe placeholders
├── .gitignore                        # Git exclusion rules
├── alembic.ini                       # Alembic CLI migration configuration
├── main.py                           # Root convenience entrypoint for 'uvicorn main:app'
├── requirements.txt                  # Python production & test dependencies
├── webapp database.md                # Legacy ERD documentation
│
├── alembic/                          # Database schema migration environment
│   ├── env.py                        # Async Alembic execution script
│   ├── script.py.mako                # Migration template file
│   └── versions/
│       ├── 549197cf5a09_initial_schema.py # Initial baseline migration (23 tables)
│       └── README.md                 # Alembic versions documentation
│
├── DETAILS/                          # Original specification & planning documents
│   ├── architecture for backend.txt  # Speculative/pre-implementation architectural notes
│   └── fundamics app 1.1.1.docx      # Product requirements document
│
├── docker/                           # Containerization and reverse proxy assets
│   ├── Dockerfile                    # Multi-stage Python 3.11-slim container image definition
│   ├── docker-compose.yml            # Multi-service stack (PostgreSQL 16, API, Nginx)
│   └── nginx.conf                    # Nginx reverse proxy, security headers & rate limits
│
├── docs/                             # Authoritative technical documentation hub
│   ├── README.md                     # Documentation index & system overview
│   ├── ARCHITECTURE.md               # High-level architecture & request lifecycle
│   ├── PROJECT_STRUCTURE.md          # Real repository structure & module map (This file)
│   ├── API.md                        # Complete 37-endpoint REST API reference
│   ├── AUTHENTICATION.md             # JWT, refresh rotation, sessions & RBAC
│   ├── DATABASE.md                   # PostgreSQL schema, 23 models, indexes & migrations
│   ├── ENVIRONMENT.md                # Environment variables reference
│   ├── BUSINESS_FLOWS.md             # Operational workflows and transaction traces
│   ├── SECURITY.md                   # Security posture, audit logs & rate limiting
│   ├── DEPLOYMENT.md                 # Local and production deployment guide
│   └── TROUBLESHOOTING.md            # Diagnostic and recovery playbooks
│
├── src/                              # Core application source code
│   ├── __init__.py
│   ├── config.py                     # Pydantic BaseSettings environment configuration
│   ├── database.py                   # Async engine, AsyncSessionLocal, and get_db dependency
│   ├── main.py                       # FastAPI application factory, middleware, exception handlers
│   │
│   ├── api/                          # HTTP Presentation Layer
│   │   └── v1/
│   │       ├── router.py             # Master v1 API aggregator
│   │       ├── health.py             # Liveness, readiness, and version endpoints
│   │       ├── auth.py               # Login, refresh, profile (/me), and logout
│   │       ├── attendance.py         # Admin student attendance preview/confirm & student summary
│   │       ├── biometric.py          # Secureye webhook, teacher summary & daily calculation
│   │       ├── results.py            # Admin exam/marks management & student result queries
│   │       ├── notes.py              # File upload, note creation, student notes & downloads
│   │       ├── system.py             # Calendar events, institute settings & audit logs
│   │       └── admin/
│   │           ├── users.py          # Admin student & teacher onboarding and roster queries
│   │           └── academics.py      # Admin classes, batches, and subjects CRUD
│   │
│   ├── core/                         # Cross-cutting system modules
│   │   ├── audit.py                  # Immutable audit log recorder with key sanitization
│   │   ├── dependencies.py           # get_current_user token verification & session validation
│   │   ├── exceptions.py             # AppException hierarchy and uniform exception handler
│   │   ├── middleware.py             # RequestContextMiddleware (X-Request-ID, timing, headers)
│   │   ├── permissions.py            # Role guards (require_admin, require_teacher, require_student)
│   │   └── security.py               # Bcrypt password hashing, JWT encoding/decoding, token hashing
│   │
│   ├── models/                       # SQLAlchemy 2.0 Declarative ORM entities (23 models)
│   │   ├── __init__.py               # Central registry for model discovery and Alembic
│   │   ├── academic.py               # Class, Batch, Subject, Enrollment
│   │   ├── auth_session.py           # AuthSession, VerificationToken, PasswordResetToken
│   │   ├── base.py                   # TimeStampedUUIDModel abstract base
│   │   ├── exam_result.py            # Exam, Result
│   │   ├── note_file.py              # FileRecord, Note
│   │   ├── student_attendance.py     # StudentAttendance, AttendanceImport, Enums
│   │   ├── system.py                 # AcademicCalendarEvent, NotificationRecord, AuditLog, InstituteSettings
│   │   ├── teacher_attendance.py     # BiometricDevice, BiometricEvent, TeacherAttendance, Enums
│   │   └── user.py                   # User, Student, Teacher, Enums
│   │
│   ├── schemas/                      # Pydantic V2 Request & Response DTOs
│   │   ├── academic.py               # Class, Batch, Subject schemas
│   │   ├── auth.py                   # Token, Login, Refresh, Password & Profile schemas
│   │   ├── exam_result.py            # Exam, Marks Entry, Publication & Summary schemas
│   │   ├── note_file.py              # Note & FileRecord schemas
│   │   ├── student_attendance.py     # Attendance preview, confirm & summary schemas
│   │   ├── system.py                 # Calendar event, Settings & Audit log schemas
│   │   ├── teacher_attendance.py     # Biometric webhook, daily & overall summary schemas
│   │   └── user.py                   # Student & Teacher creation, update & response schemas
│   │
│   └── services/                     # Domain Business Logic & Calculations
│       ├── academic_service.py       # Classes, batches, subjects creation & listing
│       ├── auth_service.py           # User authentication, token rotation, logout
│       ├── biometric_service.py      # Device webhook processing, punch deduplication, attendance calc
│       ├── note_service.py           # File storage on disk, note metadata, authorization & downloads
│       ├── result_service.py         # Exam creation, marks entry, publishing, student GPA summaries
│       ├── student_attendance_service.py # Staged attendance validation, atomic commit, analytics
│       └── user_service.py           # Student & teacher atomic registration with profile records
│
└── tests/                            # Test Suite (Pytest + HTTPX)
    ├── conftest.py                   # Test database setup, isolation fixture, client overrides
    ├── test_auth.py                  # Password hashing & JWT token validation tests
    └── test_rbac.py                  # Role permission guardrails and access denial tests
```

---

## 2. Directory & Module Responsibilities

### Root Configuration
- **[main.py](file:///d:/fundamics_backend/main.py)**: Ultra-lightweight file re-exporting `src.main.app`. Allows running `uvicorn main:app --reload` cleanly from the project root.
- **[requirements.txt](file:///d:/fundamics_backend/requirements.txt)**: Defines pinned versions of dependencies including FastAPI, SQLAlchemy (Asyncio), asyncpg, pyjwt, bcrypt, openpyxl, httpx, and pytest.
- **[.env.example](file:///d:/fundamics_backend/.env.example)**: Safe placeholder configuration template with documentation on all environment variables.

### Core Framework Modules (`src/core/`)
- **[security.py](file:///d:/fundamics_backend/src/core/security.py)**: Contains `hash_password`, `verify_password`, `hash_token`, `create_access_token`, and `decode_access_token`. Uses `bcrypt` with automated salt generation and SHA-256 for refresh token storage.
- **[dependencies.py](file:///d:/fundamics_backend/src/core/dependencies.py)**: Exposes `get_current_user`. Decodes the bearer token, verifies user active status, eager-loads student and teacher profiles, and ensures that the linked `AuthSession` has not been revoked.
- **[permissions.py](file:///d:/fundamics_backend/src/core/permissions.py)**: Implements RBAC role checks:
  - `require_admin`: Verifies `current_user.role == UserRole.ADMIN`.
  - `require_teacher`: Verifies `current_user.role == UserRole.TEACHER` and that `current_user.teacher` profile exists.
  - `require_student`: Verifies `current_user.role == UserRole.STUDENT` and that `current_user.student` profile exists.
- **[exceptions.py](file:///d:/fundamics_backend/src/core/exceptions.py)**: Defines `AppException`, `UnauthorizedError` (401), `ForbiddenError` (403), `NotFoundError` (404), `ConflictError` (409), `ValidationError` (422), `RateLimitError` (429), and the global `app_exception_handler`.
- **[middleware.py](file:///d:/fundamics_backend/src/core/middleware.py)**: `RequestContextMiddleware` intercepts every incoming HTTP request, attaches a unique `X-Request-ID`, calculates execution time in `X-Process-Time`, and injects security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`).
- **[audit.py](file:///d:/fundamics_backend/src/core/audit.py)**: Implements `record_audit_log`. Pre-filters payload keys (`password`, `token`, `secret`) to `[REDACTED]` and stores immutable records in `audit_logs`.

### API Presentation Routers (`src/api/v1/`)
- **[router.py](file:///d:/fundamics_backend/src/api/v1/router.py)**: Aggregates and prefixes all 11 sub-routers onto the unified `/api/v1` namespace.
- **[health.py](file:///d:/fundamics_backend/src/api/v1/health.py)**: Provides `/health/live`, `/health/ready` (validating database query execution), and `/version`.
- **[auth.py](file:///d:/fundamics_backend/src/api/v1/auth.py)**: Exposes `/auth/login`, `/auth/refresh`, `/auth/me`, and `/auth/logout`.
- **[admin/users.py](file:///d:/fundamics_backend/src/api/v1/admin/users.py)**: Admin-only student creation (`POST /admin/students`), student listing (`GET /admin/students`), teacher creation (`POST /admin/teachers`), and teacher listing (`GET /admin/teachers`).
- **[admin/academics.py](file:///d:/fundamics_backend/src/api/v1/admin/academics.py)**: Admin-only CRUD operations for classes, batches, and subjects.
- **[attendance.py](file:///d:/fundamics_backend/src/api/v1/attendance.py)**: Contains `admin_attendance_router` (`/admin/attendance/preview`, `/admin/attendance/confirm/{import_id}`) and `student_attendance_router` (`/student/me/attendance/summary`).
- **[biometric.py](file:///d:/fundamics_backend/src/api/v1/biometric.py)**: Contains `integrations_router` (`/integrations/biometric/secureye/events`), `teacher_attendance_router` (`/teacher/me/attendance/summary`), and `admin_teacher_attendance_router` (`/admin/teacher-attendance/{teacher_id}/calculate`).
- **[results.py](file:///d:/fundamics_backend/src/api/v1/results.py)**: Contains `admin_results_router` (`/admin/exams`, `/admin/exams/marks`, `/admin/exams/publish`) and `student_results_router` (`/student/me/results`).
- **[notes.py](file:///d:/fundamics_backend/src/api/v1/notes.py)**: Contains `admin_notes_router` (`/admin/files/upload`, `/admin/notes`) and `student_notes_router` (`/student/me/notes`, `/student/me/notes/{note_id}/download`).
- **[system.py](file:///d:/fundamics_backend/src/api/v1/system.py)**: Contains `admin_system_router` for academic calendar events, institute configuration settings, and audit logs.

### Domain Service Layer (`src/services/`)
- **[user_service.py](file:///d:/fundamics_backend/src/services/user_service.py)**: Manages atomic student and teacher creation (inserting User + Role Profile + Initial Enrollment in one transaction).
- **[auth_service.py](file:///d:/fundamics_backend/src/services/auth_service.py)**: Orchestrates password verification, refresh token hash storage, session invalidation, and token rotation.
- **[student_attendance_service.py](file:///d:/fundamics_backend/src/services/student_attendance_service.py)**: Implements staged batch validation against active enrollments, atomic attendance commit, and student summary analytics calculation.
- **[biometric_service.py](file:///d:/fundamics_backend/src/services/biometric_service.py)**: Validates device shared secret, deduplicates external punch events, maps punches to teachers, and calculates daily teacher attendance based on earliest check-in and latest check-out against institute required service hours.
- **[result_service.py](file:///d:/fundamics_backend/src/services/result_service.py)**: Handles exam containers, bulk marks insertion with maximum marks validation, publication toggling, and student result grouping with aggregate percentages.
- **[note_service.py](file:///d:/fundamics_backend/src/services/note_service.py)**: Manages file storage on local disk with SHA-256 integrity verification, creates note metadata, and enforces enrollment-scoped file streaming.
- **[academic_service.py](file:///d:/fundamics_backend/src/services/academic_service.py)**: Manages classes, batches (with class-scoped uniqueness), and subjects.

---

## 3. Discrepancies Between Speculative Documentation and Actual Implementation

During the codebase audit, multiple historical claims in `README.md` and `DETAILS/architecture for backend.txt` were found to differ from the real codebase:

| Claimed in Legacy Docs | Actual Implementation | Status |
| :--- | :--- | :--- |
| `src/repositories/` directory with 5 repo files | No `repositories/` directory exists. Queries are executed cleanly using SQLAlchemy ORM inside the `src/services/` layer. | **Architectural Simplification** |
| Separate `src/api/v1/student/` and `src/api/v1/teacher/` directories | Student and Teacher routers are co-located alongside their domain modules (e.g. `src/api/v1/attendance.py` houses both `admin_attendance_router` and `student_attendance_router`). | **Streamlined Routing** |
| "41 Endpoints registered under /api/v1" | Exactly 36 endpoints are registered under `/api/v1` (plus 1 root endpoint at `/`, totaling 37). | **Corrected in Docs** |
| 8 Test files listed in architecture text | 2 test files exist: `tests/test_auth.py` and `tests/test_rbac.py` (supported by `tests/conftest.py`). | **Corrected in Docs** |
| Argon2 password hashing via `pwdlib` | Implemented via `bcrypt` directly in `src/core/security.py`. | **Security Verified** |
| `.env.example` in repository root | File was missing from git tracking. Generated with complete placeholders. | **Added to Repository** |
