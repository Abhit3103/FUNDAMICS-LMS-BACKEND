# FUNDAMICS LMS Backend — Security Architecture & Findings

This document outlines the security controls, defensive mechanisms, data sanitization rules, and notable observations identified during the backend codebase audit.

---

## 1. Security Architecture & Controls

### 1. Cryptographic Safeguards & Password Hashing
- **Password Storage:** Passwords are never stored in plaintext. Passwords are salted and hashed using `bcrypt` via [src/core/security.py](file:///d:/fundamics_backend/src/core/security.py).
- **Token Storage:** Refresh tokens and account verification tokens are hashed with SHA-256 before insertion into the database (`auth_sessions`, `verification_tokens`, `password_reset_tokens`). If database dumps are intercepted, raw tokens cannot be recovered or used.
- **Access Tokens:** Signed with HMAC-SHA256 (`HS256`) using `settings.JWT_SECRET_KEY`. Minimum key length is enforced to prevent dictionary attacks. Access tokens expire after 15 minutes.

### 2. Session Tracking & Revocation
- Every JWT access token includes a `session_id` claim tied to a record in `auth_sessions`.
- The `get_current_user` dependency verifies that `auth_sessions.revoked_at` is `NULL`.
- Calling `POST /api/v1/auth/logout` or triggering refresh token rotation immediately invalidates prior tokens.

### 3. Insecure Direct Object Reference (IDOR) Prevention
- Student and Teacher data queries do not trust user IDs submitted in request bodies or query parameters.
- Endpoints under `/api/v1/student/me/` and `/api/v1/teacher/me/` bind query filters directly to `current_user.student.id` or `current_user.teacher.id` derived from the verified JWT payload.
- File downloads (`GET /api/v1/student/me/notes/{note_id}/download`) verify that the student's active `class_id` and `batch_id` match the note's target scope before reading the file from disk.

### 4. Audit Trail Scrubbing
The audit logging utility ([src/core/audit.py](file:///d:/fundamics_backend/src/core/audit.py)) automatically scrubs sensitive keys before storing state changes in `audit_logs`:
- Protected keys: `password`, `password_hash`, `token`, `refresh_token`, `secret`, `secret_reference`.
- Values associated with these keys are replaced with `[REDACTED]`.

### 5. HTTP Security Headers
The application injects security headers on all responses via `RequestContextMiddleware` ([src/core/middleware.py](file:///d:/fundamics_backend/src/core/middleware.py)) and Nginx ([docker/nginx.conf](file:///d:/fundamics_backend/docker/nginx.conf)):
- `X-Content-Type-Options: nosniff` (Prevents MIME-sniffing)
- `X-Frame-Options: DENY` (Mitigates clickjacking attacks)
- `Referrer-Policy: strict-origin-when-cross-origin` (Restricts referrer leakage)
- `X-XSS-Protection: 1; mode=block` (Nginx-level legacy XSS protection)

### 6. CORS Policy
Configured in [src/main.py](file:///d:/fundamics_backend/src/main.py) with explicit origin control:
- Allowed origins are read from `settings.CORS_ORIGINS` (defaults to local web and mobile ports: `3000`, `5173`, `8081`).
- Permitted methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`.
- Exposed response headers: `X-Request-ID`, `X-Process-Time`.

### 7. Reverse Proxy & Rate Limiting
Nginx ([docker/nginx.conf](file:///d:/fundamics_backend/docker/nginx.conf)) defines two distinct rate-limiting zones using client IP addresses (`$binary_remote_addr`):
- **Authentication Zone (`auth_limit`):** Protects `/api/v1/auth/` routes against brute-force credential stuffing.
  - Limit: **5 requests/second**, burst: **10** (nodelay).
- **General API Zone (`api_limit`):** Protects all other API routes against DoS/DDoS traffic.
  - Limit: **30 requests/second**, burst: **50** (nodelay).
- **Request Body Size Limit:** `client_max_body_size 25M;` limits upload payloads to prevent buffer exhaustion.

---

## 2. Codebase Audit Security Observations & Recommendations

During the audit of the backend implementation, several architectural inconsistencies and recommendations were noted:

### 1. Redundant Dependency in `requirements.txt`
- **Observation:** `requirements.txt` includes `pwdlib[argon2]>=0.2.0`, while `src/core/security.py` directly imports and uses `bcrypt`.
- **Impact:** Unnecessary bloat in Docker images; no operational vulnerability.
- **Recommendation:** Either migrate password hashing to Argon2id via `pwdlib` as originally planned in architectural notes, or prune `pwdlib[argon2]` from `requirements.txt` to keep the dependency footprint clean.

### 2. Missing Endpoints for Defined Pydantic Schemas
- **Observation:** Several schemas are fully defined in `src/schemas/` but have no corresponding route handlers in `src/api/v1/`:
  - `ChangePasswordRequest`, `ForgotPasswordRequest`, `ResetPasswordRequest` in `src/schemas/auth.py`.
  - `UpdateStudentRequest`, `UpdateTeacherRequest` in `src/schemas/user.py`.
  - `UpdateClassRequest`, `UpdateBatchRequest`, `UpdateSubjectRequest` in `src/schemas/academic.py`.
- **Impact:** Administrative updates to users and academic entities currently require direct database interaction.
- **Recommendation:** Implement corresponding `PATCH` / `PUT` endpoints in the admin routers as future product iterations require.

### 3. Pydantic `RequestValidationError` Envelope Handling
- **Observation:** Custom application errors inherit from `AppException` and return `{ success: false, error: { code, message, details }, request_id }`. However, FastAPI's built-in 422 validation errors (raised when a client submits malformed JSON that fails Pydantic schema validation) use the default FastAPI 422 JSON schema.
- **Impact:** Client applications must handle two different error response formats (one for domain errors, one for JSON schema syntax errors).
- **Recommendation:** Add an explicit exception handler for `fastapi.exceptions.RequestValidationError` in `src/main.py` to wrap validation errors in the uniform application error envelope.

### 4. File Storage Key Strategy
- **Observation:** In `src/services/note_service.py`, files are saved to disk with a UUID filename and the full path is saved in `files.storage_key`.
- **Impact:** If the storage directory path changes between environments (e.g. migrating to S3 or a mounted volume), stored paths might require database migration.
- **Recommendation:** Store relative object keys (e.g. `2026/10/<uuid>.pdf`) in `files.storage_key` and resolve absolute disk or bucket paths dynamically in the storage service.
