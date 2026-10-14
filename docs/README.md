# FUNDAMICS LMS Backend Documentation Hub

Welcome to the central technical documentation repository for the **FUNDAMICS Coaching Centre LMS Backend** (Version 1.4.0).

This documentation suite has been verified directly against the live Python source code and database migrations. The source code serves as the single source of truth.

---

## Documentation Index

| Document | Description |
| :--- | :--- |
| **[Architecture](file:///d:/fundamics_backend/docs/ARCHITECTURE.md)** | Architectural topology, layer boundaries, request lifecycle, and data flow. |
| **[Project Structure](file:///d:/fundamics_backend/docs/PROJECT_STRUCTURE.md)** | Directory tree, file responsibilities, dependencies, and component relationships. |
| **[API Specification](file:///d:/fundamics_backend/docs/API.md)** | Exhaustive reference for all 37 endpoints (methods, schemas, auth, and error states). |
| **[Authentication & RBAC](file:///d:/fundamics_backend/docs/AUTHENTICATION.md)** | JWT authentication, rotating refresh tokens, session tracking, and role-based permissions. |
| **[Database & ERD](file:///d:/fundamics_backend/docs/DATABASE.md)** | PostgreSQL 16 schema, 23 SQLAlchemy async models, ERD relationships, and Alembic migrations. |
| **[Environment Variables](file:///d:/fundamics_backend/docs/ENVIRONMENT.md)** | Complete reference of required and optional configuration keys with security notes. |
| **[Business Flows](file:///d:/fundamics_backend/docs/BUSINESS_FLOWS.md)** | End-to-end tracing of user onboarding, attendance workflows, exam results, and notes. |
| **[Security & Audit](file:///d:/fundamics_backend/docs/SECURITY.md)** | Security headers, sanitized audit logging, rate limiting, and IDOR prevention policies. |
| **[Deployment Guide](file:///d:/fundamics_backend/docs/DEPLOYMENT.md)** | Docker, Docker Compose, Nginx reverse proxy, health checks, and migration steps. |
| **[Troubleshooting](file:///d:/fundamics_backend/docs/TROUBLESHOOTING.md)** | Diagnostic playbooks for database connection, token revocation, and common failure modes. |

---

## Core System Characteristics

- **Runtime & Language:** Python 3.11+ / CPython
- **Framework:** FastAPI >=0.115.0 with Starlette
- **Database Engine:** PostgreSQL 16 (Async via `asyncpg`, sync fallback via `psycopg2-binary`)
- **ORM / Migrations:** SQLAlchemy 2.0 (AsyncSession) + Alembic 1.13.2
- **Validation Engine:** Pydantic V2 (`extra="forbid"`, `from_attributes=True`)
- **Authentication:** HS256 JWT access tokens (15-min TTL) + database-tracked rotating refresh tokens (7-day TTL)
- **Authorization:** Role-Based Access Control (`ADMIN`, `TEACHER`, `STUDENT`)
- **Total Relational Tables:** 23 models inheriting from `TimeStampedUUIDModel`
- **Total API Endpoints:** 37 active endpoints (1 root welcome, 3 health/version, 33 domain endpoints)
- **Deployment Topology:** Docker multi-stage container + Docker Compose (API, PostgreSQL, Nginx)

---

## Quick Navigation Links

- Repository Root: [README.md](file:///d:/fundamics_backend/README.md)
- Environment Template: [.env.example](file:///d:/fundamics_backend/.env.example)
- Application Entrypoint: [src/main.py](file:///d:/fundamics_backend/src/main.py)
- API v1 Router: [src/api/v1/router.py](file:///d:/fundamics_backend/src/api/v1/router.py)
- Configuration Settings: [src/config.py](file:///d:/fundamics_backend/src/config.py)
