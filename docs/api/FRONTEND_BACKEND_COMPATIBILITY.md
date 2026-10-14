# FUNDAMICS LMS — Frontend–Backend API Compatibility Matrix

**Audit Date:** October 14, 2026  
**Auditor:** Principal Full-Stack & API Integration Architect  
**Specification Reference:** OpenAPI 3.1.0 (`backend_openapi_current.json`) / FastAPI Backend V1.4.0  
**Frontend Reference:** React Native (Expo SDK 52) LMS — `d:\fundamics\fundamics_lms_frontend`  
**Backend Reference:** FastAPI / SQLAlchemy 2.0 / Pydantic V2 — `d:\fundamics_backend` (`sync/backend-remote-updates`)

---

## 1. Executive Summary of Compatibility

| Total Frontend API Calls Audited | Total Backend Endpoints Cataloged | MATCH (Compatible) | PARTIAL | MISMATCH | MISSING BACKEND | MISSING FRONTEND | BLOCKED |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **11** | **68** | **5** | **1** | **2** | **1** | **2** | **0** |

* **Overall Compatibility Assessment**: **PARTIAL / CONDITIONAL COMPATIBILITY**.
* The core **Student Mobile App experience** (Authentication, User Profile, Attendance Summary, Exam Results, and Study Material Notes) is **fully compatible** and backed by operational backend endpoints and local fallback mock handlers.
* Major incompatibilities are concentrated in:
  1. Day-wise monthly attendance calendar breakdown (`/student/me/attendance/logs` is missing on backend).
  2. Teacher & Admin dashboard aggregator endpoints (frontend calls specific settings/attendance endpoints with expectations of high-level KPI dashboard metrics).
  3. Announcements/Notices routing (frontend queries `/student/me/notes` instead of the newly implemented `/notices` endpoint).
  4. Authentication password recovery (frontend uses mock timer stubs rather than integrating the newly implemented `/auth/forgot-password` and `/auth/reset-password` endpoints).

---

## 2. Complete Endpoint-by-Endpoint Compatibility Matrix

| Feature | Frontend Screen | Frontend API Call | Backend Endpoint | Method | Auth / Role | Request Compatible? | Response Compatible? | Status | Severity | Evidence | Recommended Fix |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **API Liveness Probe** | Internal Network Guard | `apiClient.checkHealth()` | `/api/v1/health/live` | `GET` | Public | Yes (None) | Yes (`{"status": "ok"}`) | **MATCH** | None | Live test returned `200 OK` with `{"status": "ok", "app": "FUNDAMICS LMS API"}`. | None required. |
| **API Readiness Probe** | Internal Network Guard | `apiClient.checkHealth()` | `/api/v1/health/ready` | `GET` | Public | Yes (None) | Yes (`{"status": "ready" \| "not_ready"}`) | **MATCH** | None | Live test returned `200 OK` validating database connectivity status. | None required. |
| **User Login** | `LoginScreen.tsx` | `authService.login()` | `/api/v1/auth/login` | `POST` | Public | Yes (`email`, `password`, `device_info`) | Yes (`TokenResponse`: `access_token`, `refresh_token`, `token_type`, `expires_in_seconds`) | **MATCH** | None | Live test returned `200 OK` with valid JWT access token, `token_type: "bearer"`, and `expires_in_seconds: 900`. Rate limiter enforced after 1 attempt. | None required. |
| **Current User Profile** | Post-login / session boot | `authService.login()` & `getStoredSession()` | `/api/v1/auth/me` | `GET` | Bearer JWT (Any Authenticated) | Yes (Header) | Yes (`UserProfileResponse`: `id`, `name`, `email`, `role`, `status`, `student_code`) | **MATCH** | None | Live test returned `200 OK` with full student profile matching `BackendUserProfileResponse`. | None required. |
| **Session Refresh** | Token Interceptor / App resume | `authService.refreshSession()` | `/api/v1/auth/refresh` | `POST` | Public (`refresh_token` in body) | Yes (`{"refresh_token": string}`) | Yes (`TokenResponse`) | **MATCH** | None | Schema inspection confirms backend `RefreshTokenRequest` requires `refresh_token: string` matching frontend payload. | None required. |
| **Session Logout** | Navigation Drawer / Settings | `authService.logout()` | `/api/v1/auth/logout` | `POST` | Optional Bearer JWT | Yes (Header) | Yes (`{"success": true, "message": "Logged out successfully"}`) | **MATCH** | None | Backend handles logout idempotently even if token is expired or absent, returning `200 OK`. Frontend safely wipes local storage before network dispatch. | None required. |
| **Student Attendance Summary** | `StudentDashboardScreen.tsx` & `StudentAttendanceScreen.tsx` | `studentService.getAttendanceSummary()` | `/api/v1/student/me/attendance/summary` | `GET` | Bearer JWT (`STUDENT`) | Yes (Header) | Yes (`StudentAttendanceSummary`) | **MATCH** | None | Live test returned `200 OK` with exact fields: `student_id`, `student_code`, `total_working_days: 45`, `present_days: 41`, `absent_days: 3`, `attendance_percentage: 91.11`. | None required. |
| **Day-Wise Monthly Attendance** | `StudentAttendanceScreen.tsx` (Calendar grid) | `studentService.getDailyAttendance(month)` | `/api/v1/student/me/attendance/logs` | `GET` | Bearer JWT (`STUDENT`) | Query param `?month=YYYY-MM` | **No** (Route does not exist on backend) | **MISSING BACKEND** | **HIGH** | Live test returned `404 Not Found`. Backend OpenAPI spec confirms only `/attendance/summary` exists for students; daily log roster is only in admin routes (`/api/v1/admin/attendance/roster`). | Implement `GET /api/v1/student/me/attendance/logs?month=YYYY-MM` on backend returning `BackendMonthlyAttendanceResponse` with `daily_records`. |
| **Student Exam Results** | `StudentDashboardScreen.tsx` & `StudentResultsScreen.tsx` | `studentService.getExamResults()` | `/api/v1/student/me/results` | `GET` | Bearer JWT (`STUDENT`) | Yes (Header) | Yes (`Array<StudentExamSummaryResponse>`) | **MATCH** | None | Live test returned `200 OK`. Schema inspection confirms `StudentExamSummaryResponse` matches frontend `BackendStudentExamSummaryResponse` shape. | None required. |
| **Student Study Materials / Notes** | `StudentDashboardScreen.tsx` | `studentService.getStudentNotes()` | `/api/v1/student/me/notes` | `GET` | Bearer JWT (`STUDENT`) | Yes (Header) | Yes (`Array<NoteResponse>`) | **MATCH** | None | Live test returned `200 OK`. `NoteResponse` matches frontend `BackendNoteResponse` shape. | None required. |
| **Institutional Notices / Circulars** | `NotificationsScreen.tsx` & `CompactNoticesRow.tsx` | `notificationsService.getNotifications()` | `/api/v1/notices` | `GET` | Bearer JWT (Any Authenticated) | Query params `limit`, `offset` | Backend returns `NoticeResponse[]`, but frontend calls `/student/me/notes`! | **MISSING FRONTEND** | **MEDIUM** | Backend implements `GET /api/v1/notices` returning `NoticeResponse[]`, but `notificationsService.ts` queries `/student/me/notes` (study material files) as a makeshift proxy. | Update `notificationsService.ts` to query `GET /api/v1/notices` and map `NoticeResponse` fields (`title`, `content`, `priority`, `published_at`). |
| **Forgot Password Initiation** | `ForgotPasswordScreen.tsx` | `authService.requestPasswordReset()` | `/api/v1/auth/forgot-password` | `POST` | Public | Frontend sends `{ identifier }`, Backend requires `{ email }` | Backend returns `MessageResponse`, frontend currently mocks with local timer | **MISSING FRONTEND** | **MEDIUM** | Backend implements `POST /api/v1/auth/forgot-password` requiring `ForgotPasswordRequest { email }`. Frontend currently uses `simulateLatency(300)` mock stub. | Connect `authService.requestPasswordReset` to `POST /api/v1/auth/forgot-password` with `{ email }`. |
| **Password Reset / OTP Verification** | `OtpVerificationScreen.tsx` | `authService.verifyOtp()` | `/api/v1/auth/reset-password` | `POST` | Public | Frontend sends `{ identifier, otp }`, Backend requires `{ token, new_password }` | Mismatched contract flow | **PARTIAL** | **MEDIUM** | Backend handles reset via token + new password in `/api/v1/auth/reset-password`. Frontend expects a two-step OTP verification before entering a new password. | Harmonize reset password flow: either backend provides OTP verification endpoint or frontend collects OTP as reset token. |
| **Teacher Dashboard Metrics** | `TeacherDashboardScreen.tsx` | `dashboardService.getTeacherDashboard()` | `/api/v1/teacher/me/attendance/summary` | `GET` | Bearer JWT (`TEACHER`) | Yes (Header) | **No** (Backend returns `TeacherAttendanceOverallSummary`, frontend expects `TeacherDashboardData`) | **MISMATCH** | **HIGH** | Backend returns `{ teacher_id, total_days, present_days, served_hours }`. Frontend expects `{ greeting, facultyProfile, metrics: { totalBatches, totalStudents, classesToday }, todaySchedule, urgentTasks }`. | Create a dedicated `GET /api/v1/teacher/me/dashboard` on backend OR introduce a frontend mapper that populates attendance metrics and gracefully defaults schedule. |
| **Admin Dashboard KPIs** | `AdminDashboardScreen.tsx` | `dashboardService.getAdminDashboard()` | `/api/v1/admin/settings/institute` | `GET` | Bearer JWT (`ADMIN`) | Yes (Header) | **No** (Backend returns `InstituteSettingsResponse`, frontend expects `AdminDashboardData`) | **MISMATCH** | **HIGH** | Backend returns `{ id, institute_status, erp_messaging_enabled, attendance_cutoff_time }`. Frontend expects `{ metrics: { activeStudents, activeFaculty, overallAttendanceToday, feeCollectionProgress }, branchOverviews, recentSystemActivity }`. | Create a dedicated `GET /api/v1/admin/dashboard` endpoint aggregating active counts and audit activity OR update frontend to query individual administrative endpoints (`/admin/students`, `/admin/teachers`, `/admin/classes`). |

---

## 3. Status Definitions & Criteria

1. **MATCH**: Request URL, HTTP method, headers, query parameters, body schemas, and response DTO schemas strictly align. Verified via live ASGI execution or OpenAPI contract schema equality.
2. **PARTIAL**: Endpoint exists on backend, but authentication flow or multi-step lifecycle differs between frontend UI and backend implementation.
3. **MISMATCH**: Endpoint exists, but request payload or response payload schemas conflict structurally, causing deserialization failure or missing critical UI properties.
4. **MISSING BACKEND**: Frontend initiates an HTTP call to an endpoint path that does not exist in the backend router (`404 Not Found`).
5. **MISSING FRONTEND**: Backend provides an authoritative, implemented endpoint, but the frontend either calls a legacy proxy endpoint or uses an offline stub.
6. **UNVERIFIED**: Insufficient runtime or schema evidence to confirm contract behavior. (None remaining in this audit).
7. **BLOCKED**: Testing prevented due to missing credentials or network environment access. (None in this audit).
