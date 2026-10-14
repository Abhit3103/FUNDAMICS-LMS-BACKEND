# FUNDAMICS LMS Backend — Troubleshooting & Diagnostic Playbook

This document details diagnostic procedures and solutions for common operational issues encountered in development, testing, and production.

---

## 1. Database Connectivity Issues

### Error: `asyncpg.exceptions.InvalidCatalogNameError` / `Connection refused`
- **Symptom:** API fails to start, readiness probe `/api/v1/health/ready` returns `"status": "not_ready"`.
- **Root Cause:** PostgreSQL is not running or the target database does not exist.
- **Diagnostic Steps:**
  1. Check PostgreSQL container or service status:
     ```bash
     docker compose ps postgres
     ```
  2. Test direct connection:
     ```bash
     pg_isready -h localhost -p 5432 -U fundamics_app
     ```
  3. Ensure the database `fundamics_lms` has been created:
     ```sql
     SELECT 1 FROM pg_database WHERE datname = 'fundamics_lms';
     ```

### Error: `ValueError: the scheme 'postgresql' is not supported by asyncpg`
- **Symptom:** Crash on startup inside `create_async_engine`.
- **Root Cause:** `DATABASE_URL` uses `postgresql://` instead of `postgresql+asyncpg://`.
- **Solution:** Update `DATABASE_URL` in `.env` to start with `postgresql+asyncpg://`.

---

## 2. Authentication & JWT Failures

### Error: `401 Unauthorized: Access token has expired`
- **Symptom:** Client receives 401 on an authenticated endpoint.
- **Root Cause:** JWT access token lifetime (15 minutes) has elapsed.
- **Resolution:** Client application must call `POST /api/v1/auth/refresh` with the rotating refresh token to acquire a fresh access token.

### Error: `401 Unauthorized: Session has been revoked or expired`
- **Symptom:** Token signature is valid, but request is rejected.
- **Root Cause:** The `session_id` in the token claims maps to an `auth_sessions` row where `revoked_at` is set (e.g. user logged out or refresh token was rotated).
- **Resolution:** The client must perform a clean login at `POST /api/v1/auth/login`.

---

## 3. Role & Permission Denials (403 Forbidden)

### Error: `403 Forbidden: Student profile record not found` / `Teacher profile record not found`
- **Symptom:** User has role `STUDENT` or `TEACHER`, but calling `/student/me/*` or `/teacher/me/*` fails.
- **Root Cause:** The user account exists in `users`, but the corresponding 1-to-1 profile record in `students` or `teachers` was not created.
- **Solution:** Use the appropriate admin onboarding endpoint (`POST /admin/students` or `POST /admin/teachers`), which guarantees atomic creation of both the user and the role profile in one transaction.

---

## 4. Test Suite Abort & Safety Guardrails

### Error: `AssertionError: ABORT: TEST_DATABASE_URL points to Supabase!` or `ABORT: TEST_DATABASE_URL must target fundamics_test!`
- **Symptom:** `pytest` aborts immediately with an assertion error.
- **Root Cause:** `tests/conftest.py` contains safety checks to prevent test runs from altering staging, production, or Supabase databases.
- **Solution:** Verify `TEST_DATABASE_URL` targets a database named `fundamics_test` on your local PostgreSQL instance:
  ```dotenv
  TEST_DATABASE_URL=postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5433/fundamics_test
  ```

---

## 5. File Uploads & Study Material Streaming

### Error: `FileNotFoundError` or `404 Not Found: Underlying file content is unavailable`
- **Symptom:** Admin successfully uploads a file, but students cannot download it.
- **Root Cause:**
  1. The directory `./storage/notes` was deleted or is not mounted in Docker.
  2. Container permissions issue (user `fundamics` UID 1000 cannot read or write to the storage path).
- **Solution:**
  1. Ensure the directory exists with proper permissions:
     ```bash
     mkdir -p storage/notes
     chmod -R 755 storage/notes
     ```
  2. In Docker Compose, verify the volume `private_storage:/app/storage/notes` is mapped.

---

## 6. Biometric Device Webhook Ingestion

### Error: `401 Unauthorized: Invalid device credentials or device inactive`
- **Symptom:** Biometric machine punch logs are rejected by `POST /integrations/biometric/secureye/events`.
- **Root Cause:**
  1. Header `x-device-secret` is missing or incorrect.
  2. The device record in `biometric_devices` has `status != 'ACTIVE'` or `secret_reference` does not match.
- **Solution:**
  1. Confirm the pre-shared secret configured in the biometric device.
  2. Verify the corresponding row in `biometric_devices`:
     ```sql
     SELECT id, external_device_id, secret_reference, status FROM biometric_devices;
     ```
