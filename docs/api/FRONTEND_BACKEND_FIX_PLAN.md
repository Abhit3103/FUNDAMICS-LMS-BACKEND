# FUNDAMICS LMS — Frontend–Backend Remediation & Fix Plan

**Document Version:** 1.0.0  
**Audit Date:** October 14, 2026  
**Auditor:** Principal Full-Stack & Systems Architect  
**Status:** PROPOSED — PENDING USER APPROVAL BEFORE EXECUTION

---

## 1. Implementation Principles

1. **Minimal Safe Changes**: Prioritize non-breaking schema additions and isolated data-mapping fixes over broad architectural refactoring.
2. **Preserve Established Contracts**: Do not alter existing operational endpoints (`/auth/login`, `/auth/me`, `/student/me/attendance/summary`, `/student/me/results`, `/student/me/notes`) that are already 100% compatible.
3. **No Downtime / Backward Compatibility**: Frontend changes must maintain offline/fallback fixtures so mobile users never experience blank screens during network blips.
4. **Approval Required**: Strict adherence to instructions — no application code or database changes will be executed until this plan is formally reviewed and approved by the team.

---

## 2. Sequenced Implementation Phases

```
Phase A: Backend Day-Wise Attendance Route (GAP-01)
         ↓
Phase B: Frontend Notices Service Routing (GAP-04)
         ↓
Phase C: Frontend Teacher Dashboard Data Mapper (GAP-02)
         ↓
Phase D: Frontend Admin Dashboard KPI Aggregation (GAP-03)
         ↓
Phase E: Frontend Password Recovery Integration (GAP-05)
         ↓
Phase F: Full End-to-End Regression Verification
```

---

## 3. Detailed Fix Specifications

### Fix 1: Implement Student Monthly Attendance Logs Route (GAP-01)
* **File Involved (Backend):** [`d:\fundamics_backend\src\api\v1\attendance.py`](file:///d:/fundamics_backend/src/api/v1/attendance.py) & [`src/services/student_attendance_service.py`](file:///d:/fundamics_backend/src/services/student_attendance_service.py)
* **Existing Behaviour:**
  - Route does not exist in FastAPI router.
  - Client request to `GET /api/v1/student/me/attendance/logs?month=2026-09` receives `404 Not Found`.
  - Frontend falls back to static hardcoded September fixture.
* **Expected Behaviour:**
  - Endpoint returns HTTP `200 OK` with JSON matching `BackendMonthlyAttendanceResponse`:
    ```json
    {
      "month": "2026-09",
      "total_scheduled_days": 26,
      "present_days": 24,
      "absent_days": 2,
      "attendance_percentage": 92.3,
      "daily_records": [
        { "date": "2026-09-01", "status": "PRESENT", "session_count": 2, "remarks": null }
      ]
    }
    ```
* **Evidence:** Live test returned `404 Not Found`. Backend OpenAPI spec confirms only `/summary` exists for students.
* **Recommended Change:**
  - Add router endpoint `@student_attendance_router.get("/me/attendance/logs")`.
  - Query `StudentAttendance` table for the authenticated student where `attendance_date` starts with `month` (e.g. `2026-09%`).
  - Aggregate day records and compute percentage.
  - In development mode when database is offline, return synthetic day-wise records consistent with the student's summary percentage (41 present, 3 absent, 1 late).
* **Dependencies:** None. Self-contained in backend attendance router.
* **Risk:** **LOW**. Additive route; does not modify existing `/summary` endpoint.
* **Validation Procedure:**
  - Execute `GET /api/v1/student/me/attendance/logs?month=2026-09` with student Bearer token.
  - Confirm `200 OK` and verify that `StudentAttendanceScreen.tsx` renders real calendar cells.

---

### Fix 2: Connect Frontend to Authoritative Notices Endpoint (GAP-04)
* **File Involved (Frontend):** [`d:\fundamics\fundamics_lms_frontend\src\services\api\notificationsService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/notificationsService.ts) (line 95)
* **Existing Behaviour:**
  - `notificationsService.ts` makes an HTTP call to `GET /api/v1/student/me/notes` (Study Materials & DPPs) and attempts to display lecture note files as institutional notices.
* **Expected Behaviour:**
  - `notificationsService.ts` calls `GET /api/v1/notices`.
  - Maps real backend `NoticeResponse` fields:
    - `id` → `NotificationItem.id`
    - `title` → `NotificationItem.title`
    - `content` → `NotificationItem.content`
    - `priority == "URGENT"` → `NotificationItem.isUrgent: true`
    - `published_at` → formatted `NotificationItem.date`
    - `created_by` → `NotificationItem.signatory`
* **Evidence:** Backend OpenAPI spec confirms `GET /api/v1/notices` is fully implemented and returns `NoticeResponse[]`.
* **Recommended Change:**
  - In `notificationsService.ts`, change URL from `'/student/me/notes'` to `'/notices'`.
  - Update mapper function to map `NoticeResponse` shape to `NotificationItem`.
  - Retain the fallback circulars array (`MOCK_NOTIFICATIONS`) in the `catch` block if network fails.
* **Dependencies:** None.
* **Risk:** **LOW**. Strictly improves notification relevance; preserves fallback.
* **Validation Procedure:**
  - Run `useNotifications` hook in `NotificationsScreen.tsx` and verify that published institutional circulars load seamlessly.

---

### Fix 3: Resolve Teacher Dashboard Data Mapping (GAP-02)
* **File Involved (Frontend):** [`d:\fundamics\fundamics_lms_frontend\src\services\api\dashboardService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/dashboardService.ts) (line 48) & [`src/types/backend.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/types/backend.ts)
* **Existing Behaviour:**
  - Frontend directly casts the output of `GET /api/v1/teacher/me/attendance/summary` to `TeacherDashboardData`.
  - Causes missing property errors (`metrics`, `todaySchedule`, `urgentTasks`) when connected to real backend.
* **Expected Behaviour:**
  - Frontend queries `GET /api/v1/teacher/me/attendance/summary` (`TeacherAttendanceOverallSummary`).
  - Mappers synthesize `facultyProfile` from the active user session and populate attendance-driven metrics, while safely defaulting schedule items from fixtures until backend timetable scheduling is introduced.
* **Evidence:** Backend schema inspection proves endpoint only returns attendance metrics: `{ teacher_id, total_days, present_days, served_hours }`.
* **Recommended Change:**
  - In `dashboardService.ts`, create `mapBackendTeacherDashboard(summary, user)`:
    - `facultyProfile`: derived from `storageService.getUserSession()`.
    - `metrics`: map `totalBatches` (derived), `totalServedHours: summary.total_served_hours`, `presentDays: summary.present_days`.
    - `todaySchedule`: fallback to fixture schedule if backend timetable is pending.
* **Dependencies:** None.
* **Risk:** **LOW**. Client-side transformation; prevents runtime exceptions on Teacher screen.
* **Validation Procedure:**
  - Log in with Teacher credentials (`sunita.rao@fundamics.com`) and confirm `TeacherDashboardScreen.tsx` renders without crash.

---

### Fix 4: Resolve Admin Dashboard KPI Aggregation (GAP-03)
* **File Involved (Frontend):** [`d:\fundamics\fundamics_lms_frontend\src\services\api\dashboardService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/dashboardService.ts) (line 63)
* **Existing Behaviour:**
  - Frontend queries `GET /api/v1/admin/settings/institute` and casts `InstituteSettingsResponse` directly to `AdminDashboardData`.
* **Expected Behaviour:**
  - Frontend concurrently queries:
    1. `GET /api/v1/admin/students` (active students count)
    2. `GET /api/v1/admin/teachers` (active teachers count)
    3. `GET /api/v1/admin/classes` (active classes count)
    4. `GET /api/v1/admin/settings/institute` (operational institute status)
  - Aggregates them into `AdminDashboardData`.
* **Evidence:** All three admin listing endpoints (`/admin/students`, `/admin/teachers`, `/admin/classes`) exist and are tested in backend OpenAPI spec.
* **Recommended Change:**
  - In `dashboardService.ts`, replace the single `/admin/settings/institute` call with `Promise.allSettled` across `/admin/students`, `/admin/teachers`, and `/admin/classes`.
  - Populate `metrics.activeStudents = students.length`, `metrics.activeFaculty = teachers.length`.
* **Dependencies:** None. Uses existing backend admin endpoints.
* **Risk:** **LOW**. Fully utilizes existing backend endpoints.
* **Validation Procedure:**
  - Log in with Admin credentials (`admin@fundamics.com`) and confirm `AdminDashboardScreen.tsx` displays real student and faculty counts.

---

### Fix 5: Wire Password Reset Flow (GAP-05)
* **File Involved (Frontend):** [`d:\fundamics\fundamics_lms_frontend\src\services\api\authService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/authService.ts) (lines 244-271)
* **Existing Behaviour:**
  - `requestPasswordReset` and `verifyOtp` return mock timer responses.
* **Expected Behaviour:**
  - `requestPasswordReset(identifier)` maps `identifier` to `email` and dispatches `POST /api/v1/auth/forgot-password`.
  - `resetPassword(token, newPassword)` dispatches `POST /api/v1/auth/reset-password`.
* **Evidence:** Backend OpenAPI spec confirms both endpoints are operational and tested.
* **Recommended Change:**
  - Replace `simulateLatency` stubs with real `apiClient.post('/auth/forgot-password', { email })` and `apiClient.post('/auth/reset-password', { token, new_password })`.
* **Dependencies:** None.
* **Risk:** **LOW**. Eliminates mock stub.
* **Validation Procedure:**
  - Submit forgot password on `ForgotPasswordScreen.tsx` and verify network payload in development console.

---

## 4. Summary of Proposed Changes by Repository

| Repository | Files to Modify | Nature of Modification |
| :--- | :--- | :--- |
| **Backend** (`d:\fundamics_backend`) | `src/api/v1/attendance.py`, `src/services/student_attendance_service.py` | Add `GET /api/v1/student/me/attendance/logs` day-wise endpoint. |
| **Frontend** (`d:\fundamics\fundamics_lms_frontend`) | `src/services/api/notificationsService.ts` | Point to `GET /api/v1/notices` instead of `/student/me/notes`. |
| **Frontend** (`d:\fundamics\fundamics_lms_frontend`) | `src/services/api/dashboardService.ts` | Add data mappers for Teacher & Admin dashboards. |
| **Frontend** (`d:\fundamics\fundamics_lms_frontend`) | `src/services/api/authService.ts` | Connect forgot password & reset endpoints to real backend. |
