# Fundemics LMS Frontend — Backend API Integration Map

**Author**: Senior React Native Frontend Lead  
**Document Version**: 1.0.0  
**Backend Reference**: FastAPI Backend (V1.4.0) — `d:\fundamics_backend`  
**Frontend Reference**: React Native / Expo LMS — `d:\fundamics\fundamics_lms_frontend`

---

## 1. Architectural Integration Model

Network interaction strictly adheres to the layered unidirectional flow:

```
Screen View (Presentation & UI States)
      ↓
Feature Hook / State (useStudentDashboard, useAuth)
      ↓
Domain Service Layer (authService, dashboardService, studentService)
      ↓
Data Mapper (Backend DTO ↔ Frontend Domain Model)
      ↓
Central ApiClient (Base URL, Bearer Auth, 401 Interceptor, Timeout, Error Envelope)
      ↓
FastAPI Backend (REST API / PostgreSQL)
```

---

## 2. API Communication & Error Standards

### A. Base URL & Environments
* **Development Backend Base URL**: `http://localhost:8000/api/v1`
* **Configuration Variable**: `EXPO_PUBLIC_API_BASE_URL` (in `.env`)
* **Default Timeout**: 12,000ms with `AbortController` cancellation.

### B. Standard Backend Error Envelope
All error responses from the FastAPI backend return status codes 400, 401, 403, 404, 422, or 500 with the payload:
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE_STRING",
    "message": "Human readable error description",
    "details": null
  },
  "request_id": "req_84f9b201dc4e"
}
```

### C. Standard Backend Success Envelope
FastAPI endpoints return the resource DTO directly on HTTP 200/201 (e.g. `TokenResponse`, `UserProfileResponse`, `StudentAttendanceSummary`, `List[StudentExamSummaryResponse]`). The frontend API client unwraps these into typed models.

---

## 3. Comprehensive Feature-to-API Integration Matrix

### Module 1: Authentication & User Profile

| Feature | Screen | API Endpoint | HTTP Method | Request Body / Query | Response DTO | Auth Requirement | Role Requirement | Integration Status | Missing Backend Functionality |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **User Login** | `LoginScreen.tsx` | `/api/v1/auth/login` | `POST` | `{ "email": string, "password": string, "device_info"?: string }` | `{ "access_token": string, "refresh_token": string, "token_type": "bearer", "expires_in_seconds": number }` | Public | None | **Ready for Integration** | Login currently accepts email; student admission number/phone login requires email lookup on backend. |
| **Token Refresh** | `AuthContext` (Background) | `/api/v1/auth/refresh` | `POST` | `{ "refresh_token": string }` | `{ "access_token": string, "refresh_token": string, "token_type": "bearer", "expires_in_seconds": number }` | Public | None | **Ready for Integration** | None. |
| **Current User Profile** | App Startup / `AuthContext` | `/api/v1/auth/me` | `GET` | None | `{ "id": UUID, "name": string, "email": string, "phone": string, "role": string, "status": string, "student_id": UUID, "student_code": string }` | Bearer JWT | `ADMIN`, `TEACHER`, `STUDENT` | **Ready for Integration** | Does not return class name or branch name directly in profile payload. |
| **User Logout** | Header Logout Action | `/api/v1/auth/logout` | `POST` | None | `{ "success": true, "message": "Logged out successfully" }` | Bearer JWT | `ADMIN`, `TEACHER`, `STUDENT` | **Ready for Integration** | None. |
| **Forgot Password** | `ForgotPasswordScreen.tsx` | `/api/v1/auth/forgot-password` (Backend model exists, endpoint in development) | `POST` | `{ "email": string }` | `{ "success": true, "message": string }` | Public | None | **Pending Backend Route** | Backend has schema in `schemas/auth.py` (`ForgotPasswordRequest`), but endpoint route handler is currently unmounted. |
| **OTP Verification** | `OtpVerificationScreen.tsx` | `/api/v1/auth/verify-otp` | `POST` | `{ "email": string, "otp": string }` | `{ "verified": boolean }` | Public | None | **Pending Backend Route** | Backend schema exists, endpoint handler in development. |

---

### Module 2: Student Dashboard (First Vertical Slice)

| Feature | Screen | API Endpoint | HTTP Method | Request Body / Query | Response DTO | Auth Requirement | Role Requirement | Integration Status | Missing Backend Functionality |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Student Attendance Analytics** | `StudentDashboardScreen.tsx` (Attendance StatCard) | `/api/v1/student/me/attendance/summary` | `GET` | None | `{ "student_id": UUID, "student_code": string, "total_working_days": number, "present_days": number, "absent_days": number, "late_days": number, "excused_days": number, "attendance_percentage": number }` | Bearer JWT | `STUDENT` | **Ready for Integration** | None. Fully verified in `src.api.v1.attendance.get_my_attendance_summary`. |
| **Recent Assessment Scores** | `StudentDashboardScreen.tsx` (Recent Assessments Section) | `/api/v1/student/me/results` | `GET` | None | `Array<{ "exam_id": UUID, "exam_name": string, "exam_date": string, "total_marks_obtained": number, "total_max_marks": number, "overall_percentage": number, "results": Array<{ "subject_name": string, "marks_obtained": number, "max_marks": number, "percentage": number, "grade": string }> }>` | Bearer JWT | `STUDENT` | **Ready for Integration** | None. Fully verified in `src.api.v1.results.get_my_results`. |
| **Simulations Taken Count** | `StudentDashboardScreen.tsx` (Simulations StatCard) | `/api/v1/student/me/results` | `GET` | None | Derived from length of published exams array. | Bearer JWT | `STUDENT` | **Ready for Integration** | None. |
| **Student Academic Profile** | `StudentDashboardScreen.tsx` (DashboardHeader) | `/api/v1/auth/me` | `GET` | None | `{ "name": string, "student_code": string, "role": string }` | Bearer JWT | `STUDENT` | **Ready for Integration** | Profile payload contains `student_code`; class grade and branch are resolved via mapper or fallback. |
| **Today's Scheduled Classes** | `StudentDashboardScreen.tsx` (Classes Today Section) | `/api/v1/student/me/schedule/today` | `GET` | None | Not yet implemented in backend. | Bearer JWT | `STUDENT` | **Pending Backend Feature** | Backend has `Class` and `Batch` (with `start_time` and `end_time`), but does not have a daily timetable scheduler endpoint. Graceful fallback provided. |
| **Institutional Notice Board** | `StudentDashboardScreen.tsx` & `NotificationsScreen.tsx` | `/api/v1/student/me/notes` | `GET` | None | `Array<{ "id": UUID, "title": string, "description": string, "subject_name": string, "original_filename": string, "created_at": string }>` | Bearer JWT | `STUDENT` | **Integrated** | Integrated via `notificationsService.ts` mapping backend `NoteResponse` DTOs to UI notices with institutional circular fallback. |

---

### Module 3: Upcoming Modules (Reference for Future Slices)

| Feature | Screen | API Endpoint | HTTP Method | Auth Requirement | Role Requirement | Backend Availability |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Study Materials / Notes** | `ClassesScreen` / `AssignmentsScreen` | `/api/v1/student/me/notes` | `GET` | Bearer JWT | `STUDENT` | **Available** |
| **Download Note File** | Note detail | `/api/v1/student/me/notes/{note_id}/download` | `GET` | Bearer JWT | `STUDENT` | **Available** |
| **Teacher Attendance** | `TeacherDashboardScreen` | `/api/v1/teacher/me/attendance/summary` | `GET` | Bearer JWT | `TEACHER` | **Available** |
| **Admin Student Directory** | `AdminStudentsScreen` | `/api/v1/admin/students` | `GET` | Bearer JWT | `ADMIN` | **Available** |
| **Admin Teacher Directory** | `AdminTeachersScreen` | `/api/v1/admin/teachers` | `GET` | Bearer JWT | `ADMIN` | **Available** |
| **Admin Classes & Batches**| Admin Academics | `/api/v1/admin/classes`, `/api/v1/admin/batches` | `GET` | Bearer JWT | `ADMIN` | **Available** |
| **Fee Installments & Receipts**| `FeesScreen` | `/api/v1/fees/...` | `GET` | Bearer JWT | `STUDENT` / `ADMIN` | **Pending Backend** |

---

## 4. Frontend Data Mapping Architecture

To ensure strict separation of concerns, presentation components never directly touch raw backend DTO shapes:

```typescript
// Backend DTO (Exact shape from FastAPI /api/v1/student/me/attendance/summary)
interface BackendStudentAttendanceSummary {
  student_id: string;
  student_code: string;
  total_working_days: number;
  present_days: number;
  absent_days: number;
  late_days: number;
  excused_days: number;
  attendance_percentage: number;
}

// Frontend Model (Consumed by StudentDashboard Presentation UI)
interface AttendanceModel {
  percentage: number;
  presentDays: number;
  totalDays: number;
  status: 'EXCELLENT' | 'GOOD' | 'WARNING';
}
```

The mapper:
```typescript
export const mapAttendanceSummary = (dto: BackendStudentAttendanceSummary): AttendanceModel => ({
  percentage: Math.round(dto.attendance_percentage * 10) / 10,
  presentDays: dto.present_days,
  totalDays: dto.total_working_days,
  status: dto.attendance_percentage >= 90 ? 'EXCELLENT' : dto.attendance_percentage >= 75 ? 'GOOD' : 'WARNING',
});
```

---

## 5. Security & Error Handling Posture

1. **Authentication Token Lifecycle**:
   - Access token stored in memory (`apiClient`) and persisted via secure storage adapter.
   - On HTTP `401 Unauthorized`: API client intercepts and triggers automatic session invalidation without state leakage.
2. **Network Resilience**:
   - If backend is offline or unreachable, non-destructive caching displays offline banner while keeping existing dashboard data visible.
3. **No Hardcoded Secrets**:
   - Zero credentials or tokens in source code. All network endpoints derive from `EXPO_PUBLIC_API_BASE_URL`.
