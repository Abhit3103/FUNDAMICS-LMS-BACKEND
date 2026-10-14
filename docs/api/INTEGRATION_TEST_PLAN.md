# FUNDAMICS LMS — Frontend–Backend Integration Test Plan

**Document Version:** 1.0.0  
**Audit Date:** October 14, 2026  
**Auditor:** Principal Full-Stack & QA Integration Lead  
**Scope:** End-to-End & Contract Integration Testing between Expo React Native and FastAPI Backend

---

## 1. Test Environment Topology

Testing is structured across three controlled execution tiers:

1. **Tier 1: ASGI In-Memory Contract Testing (Zero-Database Dependency)**
   - Executes via Python `httpx.ASGITransport` directly against `src.main.app`.
   - Uses demo credentials fallback (`src.core.demo.py`) and mock database dependencies.
   - Purpose: Verifies HTTP status codes, router paths, Pydantic DTO schemas, and RBAC guards instantly without network or external database dependencies.
2. **Tier 2: Local Network Integration (Local Dev)**
   - Backend running via `uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload`.
   - Frontend running via `npm run web` (Expo Web on `http://localhost:8081`).
   - Purpose: Validates real browser fetch, CORS preflight (`OPTIONS`), cookies/headers, and React component state rendering.
3. **Tier 3: Staging / Cloud Preview Integration**
   - Backend deployed on Render (`https://<service-name>.onrender.com/api/v1`).
   - Connected to isolated PostgreSQL staging database.
   - Purpose: Validates cloud TLS, database transactions, and real email/notification webhook adapters.

---

## 2. Test Accounts & Credential Fixtures

The following non-destructive test accounts are available in development mode:

| Role | Test Email | Password | Primary Identifier | Student / Teacher Code | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Student** | `rohan.sharma@example.com` | `SecurePassword123!` | `rohan.sharma@example.com` | `FND-2025-1042` | Class XII scholar, active status |
| **Student (Alt)** | `aryan.srivastava@student.fundamics.in` | `SecurePassword123!` | `aryan.srivastava@student.fundamics.in` | `FND-2025-1042` | Demonstrates code-based login |
| **Teacher** | `sunita.rao@fundamics.com` | `TeacherSecurePass123!` | `sunita.rao@fundamics.com` | `TCH-001` | Mathematics faculty |
| **Admin** | `admin@fundamics.com` | `SecurePassword123!` | `admin@fundamics.com` | — | Central Administrator |

---

## 3. Integration Test Suites

### Suite 1: System Health, Metadata & Connectivity
* **Test 1.1: Liveness Probe**
  - **Request:** `GET /api/v1/health/live`
  - **Expected:** Status `200 OK`, JSON `{"status": "ok", "app": "FUNDAMICS LMS API"}`.
* **Test 1.2: Version Metadata**
  - **Request:** `GET /api/v1/version`
  - **Expected:** Status `200 OK`, JSON containing `version`, `environment: "development"`, `timezone: "Asia/Kolkata"`.
* **Test 1.3: CORS Preflight**
  - **Request:** `OPTIONS /api/v1/auth/login` with header `Origin: http://localhost:8081`, `Access-Control-Request-Method: POST`.
  - **Expected:** Status `200 OK`, `Access-Control-Allow-Origin: http://localhost:8081`, `Access-Control-Allow-Credentials: true`.

---

### Suite 2: Authentication & Session Lifecycle
* **Test 2.1: Student Authentication**
  - **Request:** `POST /api/v1/auth/login` with `{ "email": "rohan.sharma@example.com", "password": "SecurePassword123!" }`.
  - **Expected:** Status `200 OK`, response contains `access_token` (JWT string), `refresh_token`, `token_type: "bearer"`, `expires_in_seconds: 900`.
* **Test 2.2: User Profile Resolution**
  - **Request:** `GET /api/v1/auth/me` with header `Authorization: Bearer <access_token>`.
  - **Expected:** Status `200 OK`, response contains `role: "STUDENT"`, `name: "Rohan Sharma"`, `student_code: "FND-2025-1042"`.
* **Test 2.3: Anti-Spam Debounce Rate Limiter**
  - **Request:** Dispatch two consecutive login requests for the same email within 0.5s.
  - **Expected:** First request returns `200 OK`. Second request returns `429 Too Many Requests` with code `RATE_LIMIT_EXCEEDED`.
* **Test 2.4: Token Refresh Rotation**
  - **Request:** `POST /api/v1/auth/refresh` with `{ "refresh_token": "<token>" }`.
  - **Expected:** Status `200 OK`, returns new rotated `access_token` and `refresh_token`.
* **Test 2.5: Idempotent Logout**
  - **Request:** `POST /api/v1/auth/logout` with Bearer token.
  - **Expected:** Status `200 OK`, `{"success": true, "message": "Logged out successfully"}`.

---

### Suite 3: Core Student Academic Experience
* **Test 3.1: Student Attendance Summary**
  - **Request:** `GET /api/v1/student/me/attendance/summary` with student Bearer token.
  - **Expected:** Status `200 OK`, payload matches `BackendStudentAttendanceSummary`:
    - `total_working_days`: integer > 0
    - `present_days`: integer >= 0
    - `absent_days`: integer >= 0
    - `attendance_percentage`: float between 0.0 and 100.0
* **Test 3.2: Student Exam Results**
  - **Request:** `GET /api/v1/student/me/results` with student Bearer token.
  - **Expected:** Status `200 OK`, payload is an array of `StudentExamSummaryResponse` items containing `exam_id`, `exam_name`, `exam_date`, `overall_percentage`, and nested `results: ResultResponse[]`.
* **Test 3.3: Student Study Material Notes**
  - **Request:** `GET /api/v1/student/me/notes` with student Bearer token.
  - **Expected:** Status `200 OK`, payload is an array of `NoteResponse` items containing `id`, `title`, `subject_name`, `original_filename`.

---

### Suite 4: Security Boundaries & Role-Based Access Control (RBAC)
* **Test 4.1: Student Calling Admin Protected Route**
  - **Request:** `GET /api/v1/admin/settings/institute` with student Bearer token.
  - **Expected:** Status `403 Forbidden`, JSON payload:
    `{"success": false, "error": {"code": "FORBIDDEN", "message": "Administrator access required"}}`.
* **Test 4.2: Student Calling Teacher Protected Route**
  - **Request:** `GET /api/v1/teacher/me/attendance/summary` with student Bearer token.
  - **Expected:** Status `403 Forbidden`, JSON payload:
    `{"success": false, "error": {"code": "FORBIDDEN", "message": "Teacher access required"}}`.
* **Test 4.3: Unauthenticated Request to Protected Route**
  - **Request:** `GET /api/v1/student/me/attendance/summary` without Authorization header.
  - **Expected:** Status `401 Unauthorized`, JSON payload:
    `{"success": false, "error": {"code": "UNAUTHORIZED", "message": "Missing authentication token"}}`.
* **Test 4.4: Tampered JWT Token**
  - **Request:** `GET /api/v1/student/me/attendance/summary` with header `Authorization: Bearer invalid.token.payload`.
  - **Expected:** Status `401 Unauthorized`. Frontend `apiClient` triggers `unauthorizedHandler`, wipes local storage, and routes to Login.

---

### Suite 5: Error Envelope & Network Resilience
* **Test 5.1: 404 Endpoint Handling**
  - **Request:** `GET /api/v1/student/me/attendance/logs?month=2026-09`.
  - **Expected:** Status `404 Not Found`. Frontend `studentService.ts` catches 404 and safely falls back to `DEV_FIXTURE_SEPTEMBER_ATTENDANCE` without crashing UI.
* **Test 5.2: Server 500 Error Envelope Normalization**
  - **Trigger:** Internal server exception during DB outage.
  - **Expected:** Status `500 Internal Server Error`, payload matches uniform envelope:
    ```json
    {
      "success": false,
      "error": {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Human readable error description"
      },
      "request_id": "req_..."
    }
    ```
* **Test 5.3: Request Timeout Abort**
  - **Trigger:** Backend hangs exceeding `DEFAULT_TIMEOUT_MS` (12,000ms).
  - **Expected:** `AbortController` triggers `AbortError`. Frontend `apiClient` maps to `ApiError { category: 'SERVER', code: 'TIMEOUT', title: 'Connection Issue' }`.

---

## 4. Automated Execution Script

A Python test runner [`scratch/test_api_contracts.py`](file:///C:/Users/Apurv/.gemini/antigravity-ide/brain/f04a9b1d-750b-4c9c-95cd-a67a87e8f2ec/scratch/test_api_contracts.py) is available to execute these suites locally in ~3 seconds via:

```bash
d:\fundamics_backend\.venv\Scripts\python.exe scratch/test_api_contracts.py
```
