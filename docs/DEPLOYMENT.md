# FUNDAMICS LMS Backend — Deployment & Operations Guide

This guide describes how to run, test, and deploy the FUNDAMICS LMS backend in development and production environments.

---

## 1. Local Development Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 16 (running locally or via Docker)
- Git

### Step-by-Step Setup
1. **Clone the Repository:**
   ```bash
   git clone https://github.com/Abhit3103/FUNDAMICS-LMS-BACKEND.git fundamics_backend
   cd fundamics_backend
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to configure your local PostgreSQL database credentials and JWT secret.

3. **Create & Activate Virtual Environment:**
   ```bash
   python -m venv .venv
   # Windows PowerShell
   .venv\Scripts\Activate.ps1
   # Linux / macOS
   source .venv/bin/activate
   ```

4. **Install Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. **Apply Database Migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Launch Development Server:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
   - Interactive OpenAPI documentation: `http://localhost:8000/api/v1/docs`
   - ReDoc documentation: `http://localhost:8000/api/v1/redoc`
   - Health readiness probe: `http://localhost:8000/api/v1/health/ready`

---

## 2. Docker & Docker Compose Deployment

The repository includes a production-ready container stack located in `docker/`:

```
docker/
├── Dockerfile          # Python 3.11-slim application image
├── docker-compose.yml  # Orchestrates PostgreSQL, API, and Nginx
└── nginx.conf          # Reverse proxy, rate limiting, and security headers
```

### Architecture Topology in Docker

```
Internet / Clients
       │ (Port 80 / 443)
┌──────▼─────────────────────────────────────────────────┐
│ fundamics_nginx (nginx:alpine)                         │
│ - Rate limiting zones (auth_limit: 5r/s, api: 30r/s)   │
│ - Security headers & client body size (25M)            │
└──────┬─────────────────────────────────────────────────┘
       │ HTTP (api:8000)
┌──────▼─────────────────────────────────────────────────┐
│ fundamics_api (FastAPI / Uvicorn)                      │
│ - Non-root user: 'fundamics' (UID 1000)                │
│ - Health check: curl http://localhost:8000/health/ready│
│ - Volume: private_storage -> /app/storage/notes        │
└──────┬─────────────────────────────────────────────────┘
       │ TCP (postgres:5432)
┌──────▼─────────────────────────────────────────────────┐
│ fundamics_postgres (postgres:16-alpine)                │
│ - Database: fundamics_lms                              │
│ - Health check: pg_isready                             │
│ - Volume: postgres_data -> /var/lib/postgresql/data    │
└────────────────────────────────────────────────────────┘
```

### Launching the Stack
1. Ensure `.env` is configured in the repository root.
2. Navigate to the `docker/` directory:
   ```bash
   cd docker
   ```
3. Build and launch containers:
   ```bash
   docker compose up --build -d
   ```
4. Verify container statuses:
   ```bash
   docker compose ps
   ```
5. Apply database migrations inside the running API container:
   ```bash
   docker compose exec api alembic upgrade head
   ```

### Stopping the Stack
```bash
docker compose down
# To preserve data volumes, do not pass '-v'
```

---

## 3. Database Migration Management

Database migrations are managed using Alembic.

### Running Migrations
```bash
# Upgrade database to latest revision
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Generating a New Migration
When modifying or adding models in `src/models/`:
1. Ensure the model is imported in [src/models/__init__.py](file:///d:/fundamics_backend/src/models/__init__.py).
2. Generate an autodetected migration script:
   ```bash
   alembic revision --autogenerate -m "describe_schema_changes"
   ```
3. Inspect the generated migration in `alembic/versions/` before applying.

---

## 4. Running the Test Suite

The test suite uses Pytest with async fixtures:

```bash
# Run all tests
pytest tests/ -v

# Run with test coverage
pytest tests/ --cov=src -v
```

> [!IMPORTANT]
> The test configuration ([tests/conftest.py](file:///d:/fundamics_backend/tests/conftest.py)) requires a running PostgreSQL instance accessible via `TEST_DATABASE_URL` (default: `localhost:5433/fundamics_test`, as exposed by Docker Compose). The test harness uses transaction rollbacks to maintain test isolation without polluting data.

---

## 5. Production Readiness Checklist

Before moving to production:
- [ ] Set `DEBUG=false` in `.env` to disable query echo and public Swagger docs.
- [ ] Set `APP_ENV=production`.
- [ ] Generate a secure 64-character hex secret for `JWT_SECRET_KEY` (`openssl rand -hex 32`).
- [ ] Configure `CORS_ORIGINS` to strictly match your production frontend domain(s).
- [ ] Mount persistent storage for `./storage/notes` to an encrypted persistent volume.
- [ ] Set up TLS/SSL certificates in Nginx (mounting certificates to port 443).
- [ ] Verify database connection pool settings matches your PostgreSQL capacity.
