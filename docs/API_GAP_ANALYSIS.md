# FUNDAMICS LMS — API Gap Analysis & Contract Specification

**Date:** October 14, 2026  
**Auditor:** Senior Backend Engineer & Security Architect  
**Specification:** OpenAPI 3.1.0 / FastAPI Contract Matrix

---

## 1. Overview of Endpoint Coverage

| Category | Existing Endpoints | Required Endpoints | Status / Gap Identified |
| :--- | :---: | :---: | :--- |
| **Authentication & Profile** | 4 | 11 | Missing registration, verification, password management & profile update. |
| **Admin User Management** | 4 | 12 | Missing student/teacher single GET, PATCH, DELETE, and approval queues. |
| **Admin Academics** | 6 | 12 | Missing PATCH & DELETE for Classes, Batches, Subjects; missing Board support. |
| **Attendance (Student)** | 5 | 5 | Fully functional (Roster query & batch submit with Excel import). |
| **Attendance (Teacher)** | 3 | 6 | Missing admin listing, aggregate reporting, and teacher historical records. |
| **Exams & Results** | 4 | 9 | Missing exam listing, result roster query, and secure document upload/download. |
| **Notices & Announcements**| 0 | 6 | Completely missing from backend. |
| **System, Settings & Audit**| 4 | 4 | Exists, but lacks separate Institute OPEN/CLOSED toggle and ERP messaging field. |
| **Total Endpoints** | **30** | **65** | **35 Gaps Identified** |

---

## 2. Detailed Gap Matrix & Contract Specifications

### 2.1 Authentication & User Lifecycle (`/api/v1/auth`)

| Method | Endpoint | Role | Current Status | Required Contract / Fix |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/auth/login` | Public | Exists | Validated and working. |
| `POST` | `/auth/refresh` | Public | Exists | Validated and working with token rotation. |
| `GET` | `/auth/me` | Authenticated | Exists | Returns profile info. |
| `POST` | `/auth/logout` | Authenticated | Exists | Revokes active session. |
| `POST` | `/auth/register/student` | Public | **Missing** | **Body:** `{ name, email, phone, password, class_id, batch_id }`. Creates user in `PENDING_VERIFICATION` or `PENDING_APPROVAL`, generates verification token, dispatches email. |
| `POST` | `/auth/verify-email` | Public | **Missing** | **Body:** `{ token }` or `{ email, token }`. Validates token against `verification_tokens`, sets `email_verified_at`, updates status. |
| `POST` | `/auth/resend-verification` | Public | **Missing** | **Body:** `{ email }`. Resends verification email with rate limit. |
| `POST` | `/auth/forgot-password` | Public | **Missing** | **Body:** `{ email }`. Generates secure `PasswordResetToken`, dispatches reset email/SMS. |
| `POST` | `/auth/reset-password` | Public | **Missing** | **Body:** `{ token, new_password }`. Validates unexpired token and updates password hash. |
| `POST` | `/auth/change-password` | Authenticated | **Missing** | **Body:** `{ old_password, new_password }`. Validates current credentials and updates hash. |
| `PATCH`| `/auth/me` | Authenticated | **Missing** | **Body:** `{ name?, phone? }`. Allows logged-in user to update own contact info. |

---

### 2.2 Admin User Management (`/api/v1/admin`)

| Method | Endpoint | Role | Current Status | Required Contract / Fix |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/admin/students` | Admin | Exists | Creates student, user, and enrollment atomically. |
| `GET` | `/admin/students` | Admin | Exists | Queries roster with filters (`class_id`, `batch_id`). |
| `GET` | `/admin/students/{id}` | Admin | **Missing** | Returns single student record with class/batch/user details. |
| `PATCH`| `/admin/students/{id}` | Admin | **Missing** | Updates student profile (name, phone, class_id, batch_id, status). |
| `DELETE`| `/admin/students/{id}`| Admin | **Missing** | Deactivates student record (`status = INACTIVE`). |
| `POST` | `/admin/teachers` | Admin | Exists | Creates teacher and linked user account. |
| `GET` | `/admin/teachers` | Admin | Exists | Queries teacher roster. |
| `GET` | `/admin/teachers/{id}` | Admin | **Missing** | Returns single teacher record with user details. |
| `PATCH`| `/admin/teachers/{id}` | Admin | **Missing** | Updates teacher profile (name, phone, biometric ID, status). |
| `DELETE`| `/admin/teachers/{id}`| Admin | **Missing** | Deactivates teacher record (`status = INACTIVE`). |
| `GET` | `/admin/users/pending-registrations` | Admin | **Missing** | Lists pending student self-registrations awaiting review. |
| `POST` | `/admin/users/{user_id}/approve` | Admin | **Missing** | Approves student registration, transitions to `ACTIVE`, notifies student. |
| `POST` | `/admin/users/{user_id}/reject` | Admin | **Missing** | Rejects registration with reason, updates status to `REJECTED`. |

---

### 2.3 Admin Academics (`/api/v1/admin`)

| Method | Endpoint | Role | Current Status | Required Contract / Fix |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/admin/classes` | Admin | Exists | Add `board` field (CBSE, ICSE, STATE_BOARD) to payload. |
| `GET` | `/admin/classes` | Admin | Exists | Support filtering by `board` query parameter. |
| `PATCH`| `/admin/classes/{class_id}` | Admin | **Missing** | Updates class details (`name`, `board`, `academic_year`, `status`). |
| `DELETE`| `/admin/classes/{class_id}` | Admin | **Missing** | Deactivates/archives class. |
| `POST` | `/admin/batches` | Admin | Exists | Working as expected. |
| `GET` | `/admin/batches` | Admin | Exists | Filter by `class_id`. |
| `PATCH`| `/admin/batches/{batch_id}` | Admin | **Missing** | Updates batch details (`name`, `start_time`, `end_time`, `status`). |
| `DELETE`| `/admin/batches/{batch_id}` | Admin | **Missing** | Deactivates/archives batch. |
| `POST` | `/admin/subjects` | Admin | Exists | Working as expected. |
| `GET` | `/admin/subjects` | Admin | Exists | Filter by `class_id`. |
| `PATCH`| `/admin/subjects/{subject_id}` | Admin | **Missing** | Updates subject details (`name`, `status`). |
| `DELETE`| `/admin/subjects/{subject_id}` | Admin | **Missing** | Deactivates/archives subject. |

---

### 2.4 Teacher Attendance & Biometric Reporting (`/api/v1`)

| Method | Endpoint | Role | Current Status | Required Contract / Fix |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/integrations/biometric/secureye/events` | Webhook | Exists | Working (secret verified). |
| `GET` | `/teacher/me/attendance/summary` | Teacher | Exists | Working. |
| `POST` | `/admin/teacher-attendance/{teacher_id}/calculate` | Admin | Exists | Working. |
| `GET` | `/admin/teacher-attendance` | Admin | **Missing** | Lists teacher attendance records with filters (`teacher_id`, `date`, `start_date`, `end_date`, `status`). |
| `GET` | `/admin/teacher-attendance/report` | Admin | **Missing** | Returns aggregate staff attendance summary (present/absent/late/hours count). |
| `GET` | `/teacher/me/attendance/records` | Teacher | **Missing** | Teacher historical daily records with date filtering. |

---

### 2.5 Exams, Results & Scorecard Documents (`/api/v1`)

| Method | Endpoint | Role | Current Status | Required Contract / Fix |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/admin/exams` | Admin | Exists | Creates exam container. |
| `POST` | `/admin/exams/marks` | Admin | Exists | Enters marks for exam. |
| `POST` | `/admin/exams/publish` | Admin | Exists | Publishes/unpublishes results. |
| `GET` | `/student/me/results` | Student | Exists | Queries published marks. |
| `GET` | `/admin/exams` | Admin | **Missing** | Lists exams with filters (`class_id`, `batch_id`, `status`). |
| `GET` | `/admin/exams/{exam_id}` | Admin | **Missing** | Retrieves single exam detail. |
| `GET` | `/admin/exams/{exam_id}/results`| Admin | **Missing** | Retrieves student marks list and document attachment flags for an exam. |
| `POST` | `/admin/results/{result_id}/document` | Admin | **Missing** | Uploads scorecard/PDF for individual result record. |
| `GET` | `/admin/results/{result_id}/document` | Admin | **Missing** | Admin downloads student result document. |
| `GET` | `/student/me/results/{result_id}/document`| Student| **Missing** | Student downloads their own published result document. |

---

### 2.6 Notices & Announcements (`/api/v1`)

| Method | Endpoint | Role | Current Status | Required Contract / Fix |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/admin/notices` | Admin | **Missing** | Creates notice with target audience (`ALL`, `STUDENTS`, `TEACHERS`). |
| `GET` | `/admin/notices` | Admin | **Missing** | Lists notices with filters (`target_audience`, `is_active`). |
| `GET` | `/admin/notices/{notice_id}` | Admin | **Missing** | Retrieves notice details. |
| `PATCH`| `/admin/notices/{notice_id}` | Admin | **Missing** | Updates notice title, content, priority, expiry, active state. |
| `DELETE`| `/admin/notices/{notice_id}`| Admin | **Missing** | Soft-deletes / deactivates notice. |
| `GET` | `/notices` | Authenticated | **Missing** | Retrieves active notices targeted to user role (and unexpired). |

---

### 2.7 Institute Settings & Messaging Decoupling (`/api/v1/admin`)

| Method | Endpoint | Role | Current Status | Required Contract / Fix |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/admin/settings/institute` | Admin | Exists | Enhance response to return both `institute_status` ("OPEN"/"CLOSED") and `erp_messaging_enabled` (bool). |
| `PATCH`| `/admin/settings/institute` | Admin | Exists | Add `institute_status` and `erp_messaging_enabled` to request schema so they can be toggled independently. |

---

### 2.8 Notification Infrastructure Service

| Component | Responsibility | Current Status | Implementation Plan |
| :--- | :--- | :--- | :--- |
| **NotificationService** | Central dispatcher & audit tracking | Missing | Records to `notification_records` table with sent status, payload ref, error code. |
| **BrevoEmailAdapter** | Transactional emails via Brevo REST API | Missing | Validates Brevo API key, falls back to mock delivery if credentials absent. |
| **WhatsAppBusinessAdapter**| WhatsApp template & text messaging | Missing | Uses Meta Cloud API, falls back to mock delivery if credentials absent. |
