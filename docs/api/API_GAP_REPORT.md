# FUNDAMICS LMS — API Gap Analysis & Contract Gap Report

**Audit Date:** October 14, 2026  
**Auditor:** Principal Full-Stack & API Integration Architect  
**Scope:** Frontend (`d:\fundamics\fundamics_lms_frontend`) ↔ Backend (`d:\fundamics_backend`)

---

## 1. Overview & Prioritized Gap Inventory

This report documents all functional, schema, and routing discrepancies between the current React Native mobile frontend and the FastAPI backend. Each issue is categorized by business and technical severity.

| Gap ID | Feature Category | Description | Severity | Impact |
| :---: | :--- | :--- | :---: | :--- |
| **GAP-01** | **Attendance (Day-Wise Logs)** | Backend is missing `GET /api/v1/student/me/attendance/logs?month=YYYY-MM`. | **HIGH** | Student monthly calendar view falls back to mock fixture data. Real day-wise attendance cannot be viewed. |
| **GAP-02** | **Teacher Dashboard** | Schema mismatch on `GET /api/v1/teacher/me/attendance/summary`. | **HIGH** | Teacher dashboard screen cannot render real schedule or task metrics without runtime failure or fallback. |
| **GAP-03** | **Admin Dashboard** | Schema mismatch on `GET /api/v1/admin/settings/institute`. | **HIGH** | Admin dashboard screen cannot render student/teacher KPI counts or branch statistics without runtime fallback. |
| **GAP-04** | **Notices & Circulars** | Frontend queries `/student/me/notes` instead of newly implemented `GET /api/v1/notices`. | **MEDIUM** | Real institutional circulars are not displayed; student study notes (PDFs) are displayed in place of notices. |
| **GAP-05** | **Password Recovery** | Frontend uses mock stubs for forgot password & OTP instead of backend `/auth/forgot-password`. | **MEDIUM** | Password reset functionality is offline-only on mobile; users cannot initiate real password resets. |
| **GAP-06** | **Timetable / Schedule** | Backend lacks a student daily timetable schedule endpoint. | **MEDIUM** | "Today's Schedule" on Student Home Screen relies on static UI fixtures (`UpcomingClassItem[]`). |
| **GAP-07** | **Fee Management** | Fee installments & payment receipts (`/fees/...`) are not implemented on backend. | **LOW** | `FeesScreen` is currently a placeholder screen in mobile app. |
| **GAP-08** | **Document Download** | Backend provides note and result document download endpoints, but frontend UI lacks trigger. | **LOW** | PDF study materials and report card documents cannot be downloaded directly to device storage. |
| **GAP-09** | **Self-Registration** | Backend supports student registration & email verification; frontend has no registration UI. | **LOW** | Students must be manually registered by Admin or enroll through web portal. |

---

## 2. Detailed Gap Analysis & Technical Evidence

### GAP-01: Missing Student Day-Wise Monthly Attendance Endpoint
* **Severity:** **HIGH**
* **Frontend File:** [`src/services/api/studentService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/studentService.ts) (line 263)
* **Screen Affected:** `StudentAttendanceScreen.tsx` (interactive calendar grid)
* **Frontend Request:**
  - Method: `GET`
  - URL: `/api/v1/student/me/attendance/logs?month=2026-09`
  - Headers: `Authorization: Bearer <token>`
* **Expected Response Schema (`src/types/backend.ts`):**
  ```typescript
  export interface BackendMonthlyAttendanceResponse {
    month: string; // "2026-09"
    total_scheduled_days: number;
    present_days: number;
    absent_days: number;
    attendance_percentage: number;
    daily_records: Array<{
      date: string; // "YYYY-MM-DD"
      status: 'PRESENT' | 'ABSENT' | 'OFF' | 'EXCUSED';
      session_count?: number;
      remarks?: string | null;
    }>;
  }
  ```
* **Actual Backend State:**
  - Route `/api/v1/student/me/attendance/logs` does **not exist** in FastAPI router.
  - Returned HTTP Status: `404 Not Found`.
  - Backend currently only provides `/api/v1/student/me/attendance/summary` (aggregate counts: total, present, absent, percentage).
  - Admin has `/api/v1/admin/attendance/roster?date=YYYY-MM-DD`, but there is no student-scoped endpoint returning daily attendance records for an entire calendar month.
* **Evidence:** Live contract test returned `[ERROR / 404 / 500 404] GET /api/v1/student/me/attendance/logs?month=2026-09 -> 404 Not Found`.
* **Recommended Resolution:** Add `GET /api/v1/student/me/attendance/logs` to `src/api/v1/attendance.py` in the backend, querying `StudentAttendance` records filtered by `student_id` and date range matching `month`.

---

### GAP-02: Teacher Dashboard Schema Conflict
* **Severity:** **HIGH**
* **Frontend File:** [`src/services/api/dashboardService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/dashboardService.ts) (line 48)
* **Screen Affected:** `TeacherDashboardScreen.tsx`
* **Existing Behaviour:**
  - Frontend calls: `GET /api/v1/teacher/me/attendance/summary`
  - Frontend cast type: `TeacherDashboardData`
* **Contract Conflict:**
  - **Backend returns (`TeacherAttendanceOverallSummary`):**
    ```json
    {
      "teacher_id": "00000000-0000-0000-0000-000000000002",
      "teacher_code": "TCH-001",
      "total_days": 10,
      "present_days": 8,
      "absent_days": 1,
      "half_days": 1,
      "incomplete_days": 0,
      "total_served_hours": 64.5
    }
    ```
  - **Frontend expects (`TeacherDashboardData`):**
    ```typescript
    {
      greeting: string;
      facultyProfile: { name: string; department: string; designation: string; branch: string };
      metrics: { totalBatches: number; totalStudents: number; pendingAssessments: number; classesToday: number };
      todaySchedule: TeacherScheduleItem[];
      urgentTasks: TeacherTaskItem[];
    }
    ```
* **Evidence:** Inspecting `src/schemas/teacher_attendance.py` and `backend_openapi_current.json` proves the endpoint is strictly an attendance summary, not an institutional teacher dashboard aggregator.
* **Recommended Resolution:** Either:
  1. Implement a dedicated `GET /api/v1/teacher/me/dashboard` on the backend aggregating schedule, batch counts, and attendance.
  2. Or update the frontend `dashboardService.ts` to map `TeacherAttendanceOverallSummary` into `metrics` and gracefully supply fallback schedule items.

---

### GAP-03: Admin Dashboard Schema Conflict
* **Severity:** **HIGH**
* **Frontend File:** [`src/services/api/dashboardService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/dashboardService.ts) (line 63)
* **Screen Affected:** `AdminDashboardScreen.tsx`
* **Existing Behaviour:**
  - Frontend calls: `GET /api/v1/admin/settings/institute`
  - Frontend cast type: `AdminDashboardData`
* **Contract Conflict:**
  - **Backend returns (`InstituteSettingsResponse`):**
    ```json
    {
      "id": "...",
      "status": "...",
      "institute_status": "OPEN",
      "erp_messaging_enabled": true,
      "attendance_required_hours": 8,
      "timezone": "Asia/Kolkata",
      "attendance_cutoff_time": "10:30",
      "missing_checkout_policy": "MARK_HALF_DAY",
      "notifications_enabled": true
    }
    ```
  - **Frontend expects (`AdminDashboardData`):**
    ```typescript
    {
      metrics: {
        activeStudents: number;
        activeFaculty: number;
        overallAttendanceToday: number;
        feeCollectionProgress: number;
      };
      branchOverviews: BranchOverviewItem[];
      recentSystemActivity: SystemActivityItem[];
    }
    ```
* **Evidence:** Inspecting `src/schemas/system.py` confirms `InstituteSettingsResponse` contains configuration parameters, not aggregate metric counts.
* **Recommended Resolution:**
  - Backend already provides `GET /api/v1/admin/students`, `GET /api/v1/admin/teachers`, `GET /api/v1/admin/classes`.
  - Frontend `dashboardService.ts` should either aggregate these endpoints or backend should provide `GET /api/v1/admin/dashboard/summary`.

---

### GAP-04: Notice Routing Mismatch
* **Severity:** **MEDIUM**
* **Frontend File:** [`src/services/api/notificationsService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/notificationsService.ts) (line 95)
* **Screen Affected:** `NotificationsScreen.tsx` and `CompactNoticesRow.tsx`
* **Existing Behaviour:**
  - Frontend queries: `GET /api/v1/student/me/notes` (Study Materials & Notes).
  - Notes are study handouts / DPPs with PDF file attachments.
* **Backend State:**
  - Backend has now implemented a dedicated `GET /api/v1/notices` endpoint in `src/api/v1/notices.py`.
  - Returns `NoticeResponse[]` targeted to the authenticated user's role (`ALL`, `STUDENTS`, `TEACHERS`) and batch.
* **Recommended Resolution:**
  - Update `notificationsService.ts` to call `GET /api/v1/notices`.
  - Map `NoticeResponse` fields: `id`, `title`, `content`, `priority` (maps to `isUrgent`), `published_at` (maps to `date`).

---

### GAP-05: Password Recovery Mock Stub
* **Severity:** **MEDIUM**
* **Frontend File:** [`src/services/api/authService.ts`](file:///d:/fundamics/fundamics_lms_frontend/src/services/api/authService.ts) (lines 244-271)
* **Screen Affected:** `ForgotPasswordScreen.tsx` & `OtpVerificationScreen.tsx`
* **Existing Behaviour:**
  - Frontend simulates latency with `await apiClient.simulateLatency(300)` and returns simulated success.
* **Backend State:**
  - Backend has implemented:
    - `POST /api/v1/auth/forgot-password` (payload: `{ email: string }`)
    - `POST /api/v1/auth/reset-password` (payload: `{ token: string, new_password: string }`)
* **Recommended Resolution:**
  - Connect `authService.requestPasswordReset` to `POST /api/v1/auth/forgot-password`.
  - Connect `authService.resetPassword` to `POST /api/v1/auth/reset-password`.

---

## 3. Supported & Compatible Endpoint Summary

The following core modules are **100% compatible** and verified:
1. `GET /api/v1/health/live` — System Liveness
2. `GET /api/v1/health/ready` — Database Readiness
3. `GET /api/v1/version` — Application Version
4. `POST /api/v1/auth/login` — Authentication & JWT Generation
5. `GET /api/v1/auth/me` — Authenticated User Profile
6. `POST /api/v1/auth/refresh` — Rotating Token Refresh
7. `POST /api/v1/auth/logout` — Session Invalidation
8. `GET /api/v1/student/me/attendance/summary` — Student Attendance Summary
9. `GET /api/v1/student/me/results` — Student Exam Results Roster
10. `GET /api/v1/student/me/notes` — Student Study Material Files
