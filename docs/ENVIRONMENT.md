# FUNDAMICS LMS Backend — Environment Configuration Reference

This document provides the authoritative, exhaustive specification for all environment variables used by the FUNDAMICS LMS backend.

> [!CAUTION]
> **Zero Credential Exposure:** Never commit real secrets, API keys, or production database credentials to version control. Use `.env.example` as a template and provide real credentials exclusively through environment injection or a secure secrets manager.

---

## 1. Definitive Environment Variables Matrix

| Variable Name | Required / Optional | Default Value | Used By | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `APP_ENV` | Optional | `development` | `src/config.py`, `src/api/v1/health.py` | Sets environment mode (`development`, `staging`, `production`). |
| `DEBUG` | Optional | `true` | `src/config.py`, `src/database.py`, `src/main.py` | Controls SQL query echo and Swagger/Redoc UI availability (`/api/v1/docs`). Must be `false` in production. |
| `API_V1_PREFIX` | Optional | `/api/v1` | `src/config.py`, `src/main.py` | Global URL prefix prepended to all version 1 endpoints. |
| `PROJECT_NAME` | Optional | `FUNDAMICS LMS API` | `src/config.py`, `src/main.py`, `src/api/v1/health.py` | Application title reported in Swagger UI and health responses. |
| `VERSION` | Optional | `1.4.0` | `src/config.py`, `src/main.py`, `src/api/v1/health.py` | SemVer release version of the backend service. |
| `HOST` | Optional | `0.0.0.0` | `src/config.py`, `docker/Dockerfile` | Network interface binding address for the Uvicorn server. |
| `PORT` | Optional | `8000` | `src/config.py`, `docker/Dockerfile` | TCP port where Uvicorn listens for incoming HTTP traffic. |
| `TIMEZONE` | Optional | `Asia/Kolkata` | `src/config.py`, `src/api/v1/health.py`, `src/models/system.py` | Default geographical timezone for business calculations and reporting. |
| `DATABASE_URL` | **Required** in Production | `postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5432/fundamics_lms` | `src/database.py`, `alembic/env.py` | Primary asynchronous PostgreSQL connection URI (must use `postgresql+asyncpg://`). |
| `SYNC_DATABASE_URL` | Optional | `postgresql://fundamics_app:fundamics_secure_pass@localhost:5432/fundamics_lms` | `src/config.py`, `docker/docker-compose.yml` | Synchronous PostgreSQL connection URI (used as a fallback or by sync CLI tools). |
| `SUPABASE_URL` | Optional | `None` | `src/config.py` | URL for external Supabase project integration (if configured). |
| `SUPABASE_KEY` | Optional | `None` | `src/config.py` | API secret key for external Supabase project integration. |
| `JWT_SECRET_KEY` | **Required** in Production | `change_this_to_a_secure_random_hex_key_in_production_min_32_chars` | `src/core/security.py`, `src/core/dependencies.py` | High-entropy secret key (min 32 characters) used to sign and verify HS256 JWTs. |
| `JWT_ALGORITHM` | Optional | `HS256` | `src/core/security.py` | Cryptographic algorithm for signing JWTs (`HS256`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | `15` | `src/core/security.py`, `src/services/auth_service.py` | Time-to-live for access tokens before requiring refresh. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Optional | `7` | `src/services/auth_service.py` | Lifetime of refresh token sessions before re-authentication is required. |
| `STORAGE_BACKEND` | Optional | `local` | `src/config.py` | Storage provider driver. Default is `local` filesystem storage. |
| `LOCAL_STORAGE_DIR` | Optional | `./storage/notes` | `src/config.py`, `src/services/note_service.py` | Local disk folder where uploaded study material files are persisted. |
| `SECUREYE_DEVICE_SECRET` | **Required** for Biometric | `change_this_to_a_secure_shared_device_secret` | `src/config.py`, `src/services/biometric_service.py` | Shared secret token expected in the `x-device-secret` header for hardware webhook ingestion. |
| `NOTIFICATIONS_ENABLED` | Optional | `true` | `src/config.py`, `src/models/system.py` | Global master toggle for outbound notifications (SMS/WhatsApp). |
| `ERP_API_KEY` | Optional | `test_erp_key` | `src/config.py` | Secret key for external institute ERP integration webhooks. |
| `CORS_ORIGINS` | **Required** in Production | `http://localhost:3000,http://localhost:5173,http://localhost:8081` | `src/main.py` | Comma-separated list of allowed origins permitted to make cross-origin browser requests. |
| `ALEMBIC_DATABASE_URL` | Optional | `None` | `alembic/env.py` | Explicit database connection override when running Alembic CLI migrations. |
| `TEST_DATABASE_URL` | Optional | `postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5433/fundamics_test` | `tests/conftest.py`, `alembic/env.py` | Isolated PostgreSQL database URI used strictly for running Pytest suites. |

---

## 2. Environment Configuration by Deployment Stage

### Local Development
```dotenv
APP_ENV=development
DEBUG=true
DATABASE_URL=postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5432/fundamics_lms
JWT_SECRET_KEY=dev_jwt_secret_key_32_characters_long_min_value!
SECUREYE_DEVICE_SECRET=dev_shared_device_secret_value
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8081
```

### Production Deployment
```dotenv
APP_ENV=production
DEBUG=false
DATABASE_URL=postgresql+asyncpg://<db_user>:<db_pass>@<db_host>:5432/<db_name>
JWT_SECRET_KEY=<generate_with_openssl_rand_hex_32>
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
SECUREYE_DEVICE_SECRET=<high_entropy_shared_secret>
CORS_ORIGINS=https://portal.fundamics.com,https://admin.fundamics.com
LOCAL_STORAGE_DIR=/var/data/fundamics/storage/notes
```

---

## 3. Test Suite Isolation Guardrails

The Pytest configuration ([tests/conftest.py](file:///d:/fundamics_backend/tests/conftest.py)) includes hard-coded safety assertions to prevent accidental execution against production or external Supabase environments:

```python
# Safety Guardrails
assert "supabase" not in TEST_DATABASE_URL.lower(), "ABORT: TEST_DATABASE_URL points to Supabase!"
assert "fundamics_test" in TEST_DATABASE_URL.lower(), "ABORT: TEST_DATABASE_URL must target fundamics_test!"
```
These assertions ensure tests can only execute against an isolated local database containing `fundamics_test` in its name.
