# FUNDAMICS Coaching Centre LMS — Backend API (V1.4)

Secure, production-ready asynchronous FastAPI backend for the FUNDAMICS Coaching Centre Learning Management System (LMS). Built with Python 3.11+, SQLAlchemy 2.0 (Async), and PostgreSQL 16.

---

## Technical Highlights

- **Framework:** FastAPI >=0.115.0 with Uvicorn ASGI server
- **Database Engine:** PostgreSQL 16 (UTC timestamps, UUID v4 primary keys, default timezone `Asia/Kolkata`)
- **ORM & Migrations:** SQLAlchemy 2.0 (`AsyncSession`, `asyncpg`) + Alembic 1.13.2
- **Validation Engine:** Pydantic V2 (`extra="forbid"`, `from_attributes=True`)
- **Authentication & RBAC:** HS256 JWT access tokens (15-min TTL) + database-tracked rotating refresh token sessions (7-day TTL), bcrypt password hashing, zero-IDOR policy
- **Role Hierarchy:** Server-side enforcement for `ADMIN`, `TEACHER`, and `STUDENT`
- **Total Relational Models:** 23 SQLAlchemy models inheriting from `TimeStampedUUIDModel`
- **Total API Endpoints:** 37 active endpoints (1 root welcome, 3 health/version, 33 domain endpoints)
- **Deployment & Proxy:** Docker multi-stage build, Docker Compose, and Nginx reverse proxy with rate limiting

---

## Verified Directory Structure

```text
fundamics-backend/
├── .dockerignore                     # Docker build exclusion rules
├── .env.example                      # Environment variables template with safe placeholders
├── .gitignore                        # Git exclusion rules
├── alembic.ini                       # Alembic CLI migration configuration
├── main.py                           # Root convenience entrypoint for 'uvicorn main:app'
├── requirements.txt                  # Python dependencies
├── webapp database.md                # Legacy logical ERD
│
├── alembic/                          # Database schema migration environment
│   ├── env.py                        # Async Alembic execution script
│   ├── script.py.mako                # Migration template file
│   └── versions/
│       └── 549197cf5a09_initial_schema.py # Initial baseline migration (23 tables)
│
├── docker/                           # Containerization and reverse proxy assets
│   ├── Dockerfile                    # Python 3.11-slim application image
│   ├── docker-compose.yml            # Multi-service stack (PostgreSQL 16, API, Nginx)
│   └── nginx.conf                    # Nginx reverse proxy, security headers & rate limits
│
├── docs/                             # Authoritative technical documentation hub
│   ├── README.md                     # Documentation index & system overview
│   ├── ARCHITECTURE.md               # High-level architecture & request lifecycle
│   ├── PROJECT_STRUCTURE.md          # Real repository structure & module map
│   ├── API.md                        # Complete 37-endpoint REST API reference
│   ├── AUTHENTICATION.md             # JWT, refresh rotation, sessions & RBAC
│   ├── DATABASE.md                   # PostgreSQL schema, 23 models, indexes & migrations
│   ├── ENVIRONMENT.md                # Environment variables reference
│   ├── BUSINESS_FLOWS.md             # Operational workflows and transaction traces
│   ├── SECURITY.md                   # Security posture, audit logs & rate limiting
│   ├── DEPLOYMENT.md                 # Local and production deployment guide
│   └── TROUBLESHOOTING.md            # Diagnostic and recovery playbooks
│
├── src/                              # Application source code
│   ├── config.py                     # Pydantic BaseSettings environment configuration
│   ├── database.py                   # Async engine, AsyncSessionLocal, and get_db dependency
│   ├── main.py                       # FastAPI application factory, middleware, exception handlers
│   │
│   ├── api/                          # HTTP Presentation Layer
│   │   └── v1/
│   │       ├── router.py             # Master v1 API router aggregator
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
│   ├── core/                         # Cross-cutting security, middleware & exception handlers
│   │   ├── audit.py                  # Immutable audit log recorder with key sanitization
│   │   ├── dependencies.py           # get_current_user token verification & session validation
│   │   ├── exceptions.py             # AppException hierarchy and uniform exception handler
│   │   ├── middleware.py             # RequestContextMiddleware (X-Request-ID, timing, headers)
│   │   ├── permissions.py            # Role guards (require_admin, require_teacher, require_student)
│   │   └── security.py               # Bcrypt password hashing, JWT encoding/decoding, token hashing
│   │
│   ├── models/                       # 23 Relational SQLAlchemy 2.0 models
│   ├── schemas/                      # Pydantic V2 Request & Response DTOs
│   └── services/                     # Business logic, calculations & database transactions
│
└── tests/                            # Test Suite (Pytest + HTTPX)
    ├── conftest.py                   # Test database setup, isolation fixture, client overrides
    ├── test_auth.py                  # Password hashing & JWT token validation tests
    └── test_rbac.py                  # Role permission guardrails and access denial tests
```

---

## Quickstart & Local Setup

### 1. Configure Environment
```bash
cp .env.example .env
```
Update `.env` with your local database credentials and JWT secret.

### 2. Install Dependencies
```bash
python -m venv .venv
# On Windows: .venv\Scripts\Activate.ps1
# On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Apply Migrations
```bash
alembic upgrade head
```

### 4. Run Locally
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive API documentation: `http://localhost:8000/api/v1/docs`.

### 5. Run Tests
```bash
pytest tests/
```

### 6. Run with Docker Compose
```bash
cd docker
docker compose up --build -d
```
Orchestrates:
- `fundamics_postgres`: PostgreSQL 16 on port `5433:5432`
- `fundamics_api`: FastAPI on internal port `8000` with health check
- `fundamics_nginx`: Nginx reverse proxy on ports `80` and `443` with rate limiting

---

## Documentation Links

For in-depth documentation, consult the [docs/](file:///d:/fundamics_backend/docs) directory:
- [System Architecture](file:///d:/fundamics_backend/docs/ARCHITECTURE.md)
- [Project Structure Map](file:///d:/fundamics_backend/docs/PROJECT_STRUCTURE.md)
- [API Specification (37 Endpoints)](file:///d:/fundamics_backend/docs/API.md)
- [Authentication & RBAC](file:///d:/fundamics_backend/docs/AUTHENTICATION.md)
- [Database Schema & ERD (23 Models)](file:///d:/fundamics_backend/docs/DATABASE.md)
- [Environment Configuration](file:///d:/fundamics_backend/docs/ENVIRONMENT.md)
- [Business Workflows & Traces](file:///d:/fundamics_backend/docs/BUSINESS_FLOWS.md)
- [Security & Audit Controls](file:///d:/fundamics_backend/docs/SECURITY.md)
- [Deployment & Operations Guide](file:///d:/fundamics_backend/docs/DEPLOYMENT.md)
- [Troubleshooting Playbook](file:///d:/fundamics_backend/docs/TROUBLESHOOTING.md)
