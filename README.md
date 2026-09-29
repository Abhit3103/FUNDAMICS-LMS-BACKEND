# FUNDAMICS Coaching Centre LMS — Backend API (V1.4)

Secure, production-ready FastAPI backend for Coaching Centre LMS. Single system of record powered by PostgreSQL, designed for ~100–200 concurrent users.

---

## Architecture Overview

- **Framework:** FastAPI with Python 3.11+
- **Database:** PostgreSQL 16 (UTC timestamps, UUID PKs, default timezone `Asia/Kolkata`)
- **ORM & Migrations:** SQLAlchemy 2.0 (Async) + Alembic
- **Security Baseline:** Server-side RBAC (`ADMIN`, `TEACHER`, `STUDENT`), bcrypt / Argon2 hashing, rotating JWT refresh tokens, zero IDOR policy
- **Clients Supported:** React Admin Web Portal, React Native / Expo Mobile App (Role-based navigation)
- **Deployment:** Docker, Docker Compose, Nginx reverse proxy

---

## Directory Structure

```text
fundamics-backend/
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── src/
│   ├── main.py                  # App entrypoint, middleware, exception handlers
│   ├── config.py                # Pydantic V2 settings
│   ├── database.py              # Async SQLAlchemy engine & session factory
│   ├── core/
│   │   ├── security.py          # Password hashing, JWT creation/validation
│   │   ├── dependencies.py      # get_current_user
│   │   ├── permissions.py       # require_admin, require_teacher, require_student
│   │   ├── exceptions.py        # Uniform error response handlers
│   │   ├── middleware.py        # X-Request-ID, security headers, process timing
│   │   └── audit.py             # Immutable audit logger
│   ├── models/                  # 23 Relational SQLAlchemy models
│   │   ├── base.py
│   │   ├── user.py              # User, Student, Teacher
│   │   ├── academic.py          # Class, Batch, Subject, Enrollment
│   │   ├── student_attendance.py# StudentAttendance, AttendanceImport
│   │   ├── teacher_attendance.py# BiometricDevice, BiometricEvent, TeacherAttendance
│   │   ├── exam_result.py       # Exam, Result
│   │   ├── note_file.py         # FileRecord, Note
│   │   ├── system.py            # CalendarEvent, Notification, AuditLog, Settings
│   │   └── auth_session.py      # AuthSession, VerificationToken, ResetToken
│   ├── schemas/                 # Pydantic V2 request & response schemas
│   ├── services/                # Business logic & calculation engines
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   ├── academic_service.py
│   │   ├── student_attendance_service.py
│   │   ├── biometric_service.py
│   │   ├── result_service.py
│   │   └── note_service.py
│   └── api/
│       └── v1/                  # 41 Endpoints registered under /api/v1
│           ├── router.py
│           ├── auth.py
│           ├── attendance.py
│           ├── biometric.py
│           ├── results.py
│           ├── notes.py
│           ├── system.py
│           └── admin/
│               ├── users.py
│               └── academics.py
├── tests/
│   └── test_auth.py
├── .env.example
├── .gitignore
├── requirements.txt
└── alembic.ini
```

---

## Quickstart & Local Setup

### 1. Configure Environment
```bash
cp .env.example .env
```
Update `.env` with your secure secrets and database credentials.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Locally
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API docs available at: `http://localhost:8000/api/v1/docs`.

### 4. Run Tests
```bash
pytest tests/
```

### 5. Run with Docker Compose
```bash
cd docker
docker-compose up --build
```
This orchestrates `nginx` (ports 80/443), `api` (FastAPI), and `postgres` with automatic health checks.

---

## Key Modules & Rules

1. **Student Attendance (Excel Import):** Staged upload $\to$ validation $\to$ preview diff $\to$ atomic commit transaction.
2. **Teacher Attendance (Biometric):** Secureye webhook ingestion $\to$ event deduplication $\to$ daily calculation engine.
3. **Results & Marks:** Exam containers, draft vs. published state. Students query strictly their own published marks.
4. **Notes & Study Material:** Files stored in private object storage, access strictly enforced by active class/batch enrollment.
