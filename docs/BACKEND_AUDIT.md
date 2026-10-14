# FUNDAMICS LMS — Backend Architecture & Security Audit

**Date:** October 14, 2026  
**Auditor:** Senior Backend Engineer & Security Architect  
**Codebase:** FUNDAMICS LMS Backend (FastAPI / PostgreSQL / SQLAlchemy 2.x)  
**Production API Base:** `https://fundamics-lms-backend.onrender.com/api/v1`

---

## 1. Executive Summary

A comprehensive architectural, functional, and security audit of the FUNDAMICS LMS backend was conducted against the live codebase, schema definitions, and OpenAPI contract. 

The existing foundation is solidly architected:
- Clean modular layer separation (`src/api`, `src/services`, `src/models`, `src/schemas`, `src/core`).
- Async SQLAlchemy 2.0 with PostgreSQL connection pooling.
- Cryptographically secure password hashing (Argon2 / bcrypt) and rotating JWT refresh tokens (`AuthSession`).
- Strong RBAC baseline (`ADMIN`, `TEACHER`, `STUDENT`) with IDOR checks in existing attendance, notes, and results.
- 59 pre-existing automated tests passing against an isolated PostgreSQL test instance (`fundamics_test`).

However, several critical functional gaps and contract mismatches were identified that prevent full operational readiness for the Admin Web Panel and Mobile App.

---

## 2. Component-by-Component Audit Findings

### 2.1 Authentication, Authorization & User Lifecycle
* **Strengths:** 
  - Password hashing uses `pwdlib[argon2]` and `bcrypt`.
  - JWT access tokens (15-min expiry) paired with database-backed rotating refresh tokens (7-day expiry).
  - Explicit dependency injection guards (`require_admin`, `require_teacher`, `require_student`).
* **Critical Gaps:**
  - **No Student Self-Registration:** Students cannot register themselves via mobile app or portal.
  - **No Approval / Rejection Workflow:** The system lacks administrative review for incoming registrations.
  - **No Email Verification / Password Reset Endpoints:** Although models `VerificationToken` and `PasswordResetToken` exist in `src/models/auth_session.py`, no corresponding API routes or service flows were implemented.
  - **No Password Management:** No change password or reset password endpoints.
  - **No Self Profile Update:** Authenticated users cannot update their own allowed profile details (`phone`, `name`).

### 2.2 Academic Hierarchy & Board Support
* **Strengths:**
  - Clean relationship hierarchy (`Class` $\to$ `Batch` $\to$ `Subject` $\to$ `Enrollment`).
  - Unique constraints prevent duplicate codes per class/batch.
* **Critical Gaps:**
  - **Missing Academic Board Support:** `Class` lacks a `board` specification (e.g., `CBSE`, `ICSE`, `STATE_BOARD`), which is required by coaching centres operating multi-board curriculums.
  - **Incomplete CRUD:** Academic administration endpoints only supported `POST` (create) and `GET` (list). Missing `PATCH` (update) and `DELETE` (deactivate) for classes, batches, and subjects.

### 2.3 Student & Teacher User Administration
* **Strengths:**
  - Atomic transactions for user creation and enrollment.
  - Audit logging for user creation.
* **Critical Gaps:**
  - No single user lookup (`GET /api/v1/admin/students/{id}`, `GET /api/v1/admin/teachers/{id}`).
  - No update endpoints (`PATCH /api/v1/admin/students/{id}`, `PATCH /api/v1/admin/teachers/{id}`).
  - No status toggles or deactivation endpoints.

### 2.4 Teacher Attendance & Biometric Integration
* **Strengths:**
  - Secureye biometric webhook ingestion with secret validation and event deduplication.
  - Daily calculation engine for working hours.
* **Critical Gaps:**
  - No listing endpoint for teacher attendance (`GET /api/v1/admin/teacher-attendance`).
  - No reporting / aggregate summary endpoint for staff attendance.
  - Teachers cannot view their historical attendance records (`/teacher/me/attendance/records`).

### 2.5 Exams, Results & Student Result Documents
* **Strengths:**
  - Exams support draft vs. published state.
  - Students can query only their own published results.
* **Critical Gaps:**
  - **No Exam Listing:** Admin has no endpoint to list created exams (`GET /api/v1/admin/exams`).
  - **No Exam Results Roster:** Admin cannot view marks entered for a specific exam (`GET /api/v1/admin/exams/{id}/results`).
  - **Missing Result Document Upload:** `Result` model has no link to `FileRecord`. Admin cannot upload student scorecards/answer sheets, and students cannot download their scorecards.

### 2.6 Notices & Announcements
* **Findings:**
  - The feature is completely missing. No database model, no service, and no API endpoints exist.
  - Coaching institutes require institute-wide and targeted announcements (for classes, batches, teachers, or students).

### 2.7 Institute Settings & ERP Messaging Separation
* **Strengths:**
  - Singleton `InstituteSettings` model storing working hours and timezone.
* **Critical Gaps:**
  - `InstituteSettings` mixed generic institute status (`ACTIVE`) with messaging toggles.
  - Institute OPEN/CLOSED operational status must be strictly decoupled from ERP notification delivery (ON/OFF).
  - Update schema did not permit updating status.

### 2.8 Notification Infrastructure
* **Findings:**
  - Only `NotificationRecord` table exists.
  - No outbound email adapter (Brevo) or WhatsApp Business adapter is implemented.
  - Notification triggers are not integrated into core events (registration, password reset, exam publication).

---

## 3. Security & Compliance Review

| Security Area | Current Status | Risk Level | Remediations Required |
| :--- | :--- | :--- | :--- |
| **Password Storage** | Argon2id / bcrypt hashing | Low (Secure) | Maintain password complexity requirements on all new endpoints. |
| **Authentication** | Rotating refresh tokens, 15m JWT | Low (Secure) | Add rate-limiting on sensitive auth routes (`/register`, `/forgot-password`). |
| **Authorization (RBAC)** | Strict role checks | Medium | Add ownership verification for result document downloads. |
| **File Storage** | Local storage with SHA256 checksums | Medium | Prevent path traversal, enforce MIME validation, and restrict access by role/enrollment. |
| **Audit Logging** | Immutable `audit_logs` table | Low (Good) | Record audit logs on all new admin actions (approvals, updates, notice creation). |
| **Database Migrations** | Alembic with transactional DDL | Low (Safe) | Create safe non-destructive migration scripts preserving all existing data. |

---

## 4. Remediation Plan

The remediation follows a 4-phase non-destructive execution:
1. **Schema & Migration Layer:** Update models safely and generate an Alembic migration for board support, result document references, notices, and institute settings.
2. **Services & Infrastructure:** Implement Brevo/WhatsApp notification adapters, auth token verification, notice engine, and teacher attendance reporting.
3. **API Endpoints:** Implement and wire all missing routes under `/api/v1`.
4. **Validation & Documentation:** Run comprehensive automated tests against isolated test database, regenerate `openapi.json`, and finalize documentation deliverables.
