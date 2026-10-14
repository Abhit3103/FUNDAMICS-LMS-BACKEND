# FUNDAMICS LMS — Authentication & Security Lifecycle Audit

**Audit Date:** October 14, 2026  
**Auditor:** Principal Full-Stack & Security Architect  
**Specification:** OAuth2 Bearer JWT / FastAPI Security Dependencies / React Native Auth Architecture  
**Target Environments:** Local Development (`http://127.0.0.1:8000`), Expo Web (`http://localhost:8081`), Mobile App

---

## 1. Authentication Architecture Overview

Network authentication adheres to an isolated, layered flow between the client device and the FastAPI backend:

```
[Login Screen / AuthContext]
         │
         ▼
[authService.login(credentials)]
         │
         ▼ (POST /api/v1/auth/login)
[FastAPI AuthService] ──(Checks Rate Limiter: 5 req/min, 1.5s debounce)
         │
         ├──(Validates Bcrypt Password Hash against Postgres User table)
         └──(Generates JWT HS256 Access Token [15m] + Rotating Refresh Token [7d])
         │
         ▼
[apiClient.setToken(accessToken)]
         │
         ▼ (GET /api/v1/auth/me with Bearer Header)
[FastAPI get_current_user] ──(Decodes JWT, validates active session in DB)
         │
         ▼
[storageService.setAuthToken & setUserSession]
         │
         ▼
[AuthContext state -> isAuthenticated: true, user: User]
```

---

## 2. Step-by-Step Lifecycle Verification

### Step 1: Login Request
* **Endpoint:** `POST /api/v1/auth/login`
* **Rate Limiting Guard:** Guarded by `rate_limit_login` dependency and `login_rate_limiter.check(email)`:
  - Max requests: 5 per 60-second sliding window.
  - Debounce: Minimum 1.5 seconds between requests targeting the same IP or email.
  - Rejection code: `429 RateLimitError` (`"A login request is already being processed. Please avoid multiple rapid submissions."`).
* **Frontend Payload:**
  ```json
  {
    "email": "rohan.sharma@example.com",
    "password": "SecurePassword123!",
    "device_info": "Fundemics Mobile (web)"
  }
  ```
* **Identifier Normalization:** Frontend `authService.ts` checks if identifier contains `@`. If student provides student code (e.g. `FND-2025-1042`), it appends `@student.fundamics.in` before dispatching to the backend, ensuring compatibility with backend email-based lookup.

### Step 2: Login Response
* **HTTP Status:** `200 OK`
* **Backend DTO:** `TokenResponse`
* **Response Payload:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "uYjL7z6-2kXN...",
    "token_type": "bearer",
    "expires_in_seconds": 900
  }
  ```
* **Token Specifications:**
  - Algorithm: `HS256`
  - Claims: `{"sub": "<UUID>", "role": "STUDENT", "session_id": "<UUID>", "exp": <timestamp>, "iat": <timestamp>}`
  - Access Token TTL: 15 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES = 15`)
  - Refresh Token TTL: 7 days (`REFRESH_TOKEN_EXPIRE_DAYS = 7`)

### Step 3: Current User Query & Role Resolution
* **Endpoint:** `GET /api/v1/auth/me`
* **Header:** `Authorization: Bearer <access_token>`
* **HTTP Status:** `200 OK`
* **Backend DTO:** `UserProfileResponse`
* **Response Payload:**
  ```json
  {
    "id": "00000000-0000-0000-0000-000000000003",
    "name": "Rohan Sharma",
    "email": "rohan.sharma@example.com",
    "phone": "9876543210",
    "role": "STUDENT",
    "status": "ACTIVE",
    "student_id": "172a8861-3a04-42aa-9e56-5fcd5f74c36b",
    "teacher_id": null,
    "student_code": "FND-2025-1042",
    "teacher_code": null
  }
  ```
* **Role Verification:** Frontend mapper extracts `profile.role` (`STUDENT`, `TEACHER`, or `ADMIN`) and sets navigation stack accordingly (`StudentNavigator`, `TeacherNavigator`, or `AdminNavigator`).

### Step 4: Token Storage & Session Persistence
* **Storage Engine:** React Native `AsyncStorage` via [`src/services/storage/storageService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/storage/storageService.ts).
* **Storage Keys:**
  - `@fundamics:auth_token`: Stores raw access token string.
  - `@fundamics:refresh_token`: Stores rotating refresh token string.
  - `@fundamics:user_session`: Stores serialized `User` profile JSON.
* **App Boot Restoration:** [`AuthContext.tsx`](file:///d:/fundamics/fundamics_lms_frontend/src/app/providers/AuthContext.tsx) calls `authService.getStoredSession()` on mount. If a stored token and user profile exist, `apiClient.setToken(token)` is populated immediately without re-prompting for credentials.

### Step 5: Authenticated API Requests
* **Interception:** [`apiClient.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/apiClient.ts) automatically checks `this.authToken`. If populated, injects:
  `Authorization: Bearer <authToken>` into all outbound requests.
* **Format:** Exact Bearer format required by FastAPI `HTTPBearer` security dependency.

### Step 6: 401 Unauthorized Interceptor & Session Expiry
* **Interceptor:** If any request returns `401 Unauthorized`:
  1. Checks if the request is already a logout call (`endpoint.includes('/auth/logout')`) to prevent infinite recursion.
  2. Debounces with `isHandlingUnauthorized` flag.
  3. Invokes `unauthorizedHandler()` registered by `AuthContext.tsx`.
  4. Clears local tokens and redirects user to `LoginScreen`.

### Step 7: Token Refresh Flow
* **Endpoint:** `POST /api/v1/auth/refresh`
* **Request:** `{"refresh_token": "<refreshToken>"}`
* **Response:** Returns new access token and new rotated refresh token.
* **Storage:** Updates both tokens in `AsyncStorage`. If refresh fails (e.g., token expired or revoked in database), triggers clean logout.

### Step 8: Logout Execution & Idempotency
* **Endpoint:** `POST /api/v1/auth/logout`
* **Execution Sequence:**
  1. Frontend **immediately** wipes in-memory token (`apiClient.setToken(null)`).
  2. Frontend **immediately** clears persistent storage (`storageService.clearAuth()`).
  3. Frontend dispatches `POST /api/v1/auth/logout` with Bearer header asynchronously (best-effort).
  4. Backend marks database session status as `REVOKED`. If token is already invalid, backend returns `200 OK` idempotently.
  5. Any network error during logout is caught and suppressed, ensuring the client UI is never trapped in a broken logged-in state.

---

## 3. Role-Based Access Control (RBAC) Verification

The backend enforces authorization at the router level via dependency injection:
* `require_admin(user: User)`: Verifies `user.role == UserRole.ADMIN`.
* `require_teacher(user: User)`: Verifies `user.role == UserRole.TEACHER`.
* `require_student(user: User)`: Verifies `user.role == UserRole.STUDENT`.

### Live Contract RBAC Test Results:

| Test Scenario | Caller Role | Target Endpoint | Target Role | Expected Status | Actual Status | Backend Error Code | Result |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| Student calls Admin Settings | `STUDENT` | `GET /api/v1/admin/settings/institute` | `ADMIN` | `403 Forbidden` | **403** | `FORBIDDEN` | **PASS** |
| Student calls Teacher Attendance | `STUDENT` | `GET /api/v1/teacher/me/attendance/summary` | `TEACHER` | `403 Forbidden` | **403** | `FORBIDDEN` | **PASS** |
| Unauthenticated calls Student API | None | `GET /api/v1/student/me/attendance/summary` | `STUDENT` | `401 Unauthorized` | **401** | `UNAUTHORIZED` | **PASS** |
| Admin calls Admin Settings | `ADMIN` | `GET /api/v1/admin/settings/institute` | `ADMIN` | `200 OK` | **200** | — | **PASS** |

**Conclusion:** Frontend navigation guards are reinforced by strict backend HTTP 403 authorization dependencies. Privilege escalation is blocked.

---

## 4. Security Findings & Recommendations

1. **Local Storage Security (Low-Medium Risk on Mobile):**
   - *Current Implementation:* Tokens are stored in standard `AsyncStorage`.
   - *Recommendation:* For standalone production iOS/Android binaries, migrate sensitive JWT storage to `expo-secure-store` (iOS Keychain / Android Keystore) to protect tokens against rooted devices.
2. **Access Token Expiration (Well Configured):**
   - Short TTL of 15 minutes limits the blast radius of any compromised access token.
3. **Rate Limiting Protection (Well Configured):**
   - In-memory rate limiter protects against automated credential brute-forcing and duplicate click spamming.
4. **CORS Origins (Configured for Dev):**
   - Development allows `localhost:8081` and `127.0.0.1:8081`. Production must ensure only verified web domains are added to `PRODUCTION_CORS_ORIGINS`.
