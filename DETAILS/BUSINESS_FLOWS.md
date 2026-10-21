# FUNDAMICS LMS Backend — Business Workflows & Execution Traces

This document traces the primary business flows of the FUNDAMICS LMS backend, mapping the execution path through Route $\to$ Dependency $\to$ Service $\to$ Database $\to$ Audit Log $\to$ Response.

---

## 1. Student Onboarding & Enrollment Flow

### Overview
Administrators onboard students directly. The backend validates academic references, provisions the underlying user authentication record, builds the student profile, and establishes the active class enrollment within an atomic transaction.

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Route as POST /admin/students
    participant Guard as require_admin
    participant Service as UserService
    participant DB as PostgreSQL (asyncpg)

    Admin->>Route: Submit CreateStudentRequest
    Route->>Guard: Verify Admin Role
    Guard-->>Route: Admin User Confirmed
    Route->>Service: create_student(db, req, actor_id)
    Service->>DB: Check email uniqueness (users)
    Service->>DB: Check student_code uniqueness (students)
    Service->>DB: Validate class_id exists (classes)
    Service->>DB: Validate batch_id belongs to class_id (batches)
    Service->>Service: Hash password via bcrypt
    Service->>DB: Insert User (role=STUDENT, status=ACTIVE)
    Service->>DB: Flush & get user.id
    Service->>DB: Insert Student (user_id, student_code, class_id, batch_id)
    Service->>DB: Flush & get student.id
    Service->>DB: Insert Enrollment (student_id, class_id, batch_id, start_date)
    Service->>DB: Insert sanitized AuditLog (STUDENT_CREATED)
    Service->>DB: Commit Transaction
    Service-->>Route: Return StudentResponse
    Route-->>Admin: 201 Created (Student DTO)
```

### Business Rules & Safeguards
1. **Email Uniqueness:** Rejects duplicates with `409 Conflict`.
2. **Student Code Uniqueness:** Code must be unique across the entire institute; rejects duplicates with `409 Conflict`.
3. **Hierarchy Integrity:** Validates `batch.class_id == req.class_id`. A student cannot be assigned to a batch belonging to another class (`422 Unprocessable Entity`).
4. **Temporary Password Generation:** If an admin leaves the password empty, the system generates a secure 12-character random string via `secrets.token_urlsafe(12)`.
5. **Atomic Commit:** If any part of the user, student profile, or enrollment fails, the entire transaction rolls back cleanly.

---

## 2. Student Attendance Two-Phase Staging Flow

### Overview
Student attendance is processed using a two-stage pattern (Stage 1: Preview & Validate $\to$ Stage 2: Confirm & Commit) to prevent corrupted or duplicate records.

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant Route as POST /admin/attendance/preview
    participant Service as StudentAttendanceService
    participant DB as PostgreSQL

    Admin->>Route: Form-data (class_id, batch_id, date, records[])
    Route->>Service: parse_and_validate_records(...)
    Service->>DB: Load active enrolled students for class & batch
    Service->>DB: Check existing attendance for class/batch on date
    loop For each submitted record
        Service->>Service: Check code present in enrolled set
        Service->>Service: Check code not duplicated in payload
        Service->>Service: Verify no existing record in DB on that date
        Service->>Service: Validate status enum (PRESENT, ABSENT, etc.)
    end
    Service->>DB: Insert AttendanceImport (status=VALIDATED / FAILED)
    Service->>DB: Commit Transaction
    Service-->>Admin: Return AttendanceImportPreviewResponse with row-level error breakdown

    Note over Admin,Route: Admin reviews diff & resolves discrepancies

    Admin->>Route: POST /admin/attendance/confirm/{import_id}
    Route->>Service: commit_import(import_id, validated_rows)
    Service->>DB: Verify import.status != COMPLETED
    Service->>DB: Bulk insert StudentAttendance records
    Service->>DB: Update import.status = COMPLETED
    Service->>DB: Insert AuditLog (ATTENDANCE_IMPORTED)
    Service->>DB: Commit Transaction
    Service-->>Admin: 200 OK (Committed rows count)
```

### Business Rules & Safeguards
- **Duplicate Prevention:** The database enforces a `UNIQUE(student_id, date)` constraint. The validation stage proactively verifies this constraint before inserting rows.
- **Strict Roster Scoping:** Unenrolled students are rejected with an explicit validation error: `"Student code 'XYZ' not enrolled in this class/batch"`.
- **Zero IDOR Analytics:** When students request their attendance summary (`/student/me/attendance/summary`), the endpoint reads `current_user.student.id` directly from the authenticated session, ensuring students can never query other students' attendance.

---

## 3. Biometric Ingestion & Teacher Attendance Calculation

### Overview
Integrates physical Secureye biometric devices via webhook ingestion followed by administrative calculation against institute service hours.

```mermaid
sequenceDiagram
    autonumber
    actor Device as Biometric Machine
    participant Webhook as POST /integrations/biometric/secureye/events
    participant BioService as BiometricService
    participant DB as PostgreSQL
    actor Admin
    participant CalcRoute as POST /admin/teacher-attendance/{id}/calculate

    Device->>Webhook: Events payload + Header x-device-secret
    Webhook->>BioService: ingest_device_events(device_secret, events)
    BioService->>DB: Verify active BiometricDevice matching secret
    BioService->>DB: Load active teachers map (biometric_employee_id)
    loop Each event in payload
        BioService->>DB: Check UNIQUE(device_id, external_event_id)
        alt Duplicate Event
            BioService->>BioService: Increment duplicates_skipped counter
        else New Event
            BioService->>DB: Insert BiometricEvent (linked to teacher_id if matched)
        end
    end
    BioService->>DB: Commit & Log Audit
    BioService-->>Device: 200 OK (Processed count)

    Note over Admin,CalcRoute: End of day: Admin initiates daily calculation

    Admin->>CalcRoute: Trigger calculate for teacher_id on date
    CalcRoute->>BioService: calculate_teacher_daily(teacher_id, target_date)
    BioService->>DB: Query InstituteSettings for required_hours (default 8)
    BioService->>DB: Query BiometricEvents for teacher on target_date
    alt No events found
        BioService->>DB: Insert TeacherAttendance(status=ABSENT, served_minutes=0)
    else Punches found
        BioService->>BioService: Earliest IN punch and latest OUT punch
        BioService->>BioService: Calculate served_minutes = check_out - check_in
        BioService->>BioService: Determine status: PRESENT, HALF_DAY, INCOMPLETE, or REVIEW_REQUIRED
        BioService->>DB: Insert TeacherAttendance record
    end
    BioService->>DB: Commit Transaction
    BioService-->>Admin: Return TeacherAttendanceDaySummary
```

---

## 4. Exam Results Lifecycle & GPA Calculation

### Overview
Handles the academic evaluation lifecycle: Exam container creation $\to$ Bulk marks entry $\to$ Administrative publication $\to$ Student report card access.

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant AdminRoute as Admin Results API
    participant ResultService as ResultService
    participant DB as PostgreSQL
    actor Student
    participant StudentRoute as GET /student/me/results

    Admin->>AdminRoute: POST /admin/exams (name, class_id, date)
    AdminRoute->>ResultService: create_exam(...)
    ResultService->>DB: Insert Exam (status=SCHEDULED)
    ResultService-->>Admin: Exam Created

    Admin->>AdminRoute: POST /admin/exams/marks (exam_id, entries[])
    AdminRoute->>ResultService: record_bulk_marks(...)
    loop Each student score entry
        ResultService->>ResultService: Validate marks_obtained <= max_marks
        ResultService->>DB: Upsert Result (exam_id, student_id, subject_id)
    end
    ResultService->>DB: Update Exam status = MARKS_ENTERED
    ResultService-->>Admin: Marks Recorded

    Admin->>AdminRoute: POST /admin/exams/publish (exam_id, publish=true)
    AdminRoute->>ResultService: toggle_publication(exam_id, true)
    ResultService->>DB: Update Result.published_at = now()
    ResultService->>DB: Update Exam status = PUBLISHED
    ResultService-->>Admin: Results Published

    Note over Student,StudentRoute: Student views results

    Student->>StudentRoute: Authenticated request
    StudentRoute->>ResultService: get_student_results(student_id)
    ResultService->>DB: Query Result WHERE student_id = :id AND published_at IS NOT NULL
    ResultService->>ResultService: Group by exam_id
    ResultService->>ResultService: Calculate total marks, max marks, overall percentage
    ResultService-->>Student: Return StudentExamSummaryResponse[]
```

### Business Rules & Safeguards
1. **Score Bound Invariant:** `marks_obtained` must never exceed `max_marks`. Rejects invalid inputs with `422 Unprocessable Entity`.
2. **Draft Result Privacy:** Results with `published_at IS NULL` are strictly hidden from student queries. Even if marks are saved in the database, students cannot view them until the admin explicitly triggers `/admin/exams/publish`.
3. **Compound Key Uniqueness:** Results are constrained by `UNIQUE(exam_id, student_id, subject_id)`. Re-submitting marks for an existing exam/student/subject cleanly updates the score.

---

## 5. Notes & Study Materials Upload & Authorization Flow

### Overview
Manages uploaded educational materials stored in local private disk storage (`./storage/notes`) and ensures access is restricted to students actively enrolled in the relevant class and batch.

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant UploadRoute as POST /admin/files/upload
    participant NoteRoute as POST /admin/notes
    participant NoteService as NoteService
    participant Disk as Local Storage (./storage/notes)
    participant DB as PostgreSQL
    actor Student
    participant DownloadRoute as GET /student/me/notes/{id}/download

    Admin->>UploadRoute: Upload binary file (Multipart)
    UploadRoute->>NoteService: upload_file(file, actor_id)
    NoteService->>NoteService: Compute SHA-256 checksum
    NoteService->>Disk: Save file as {uuid}.ext
    NoteService->>DB: Insert FileRecord(storage_key, mime, size, checksum)
    NoteService-->>Admin: Return FileRecordResponse (with file_id)

    Admin->>NoteRoute: Create Note (title, class_id, batch_id, subject_id, file_id)
    NoteRoute->>NoteService: create_note(...)
    NoteService->>DB: Validate subject and batch belong to class
    NoteService->>DB: Insert Note (linked to FileRecord)
    NoteService-->>Admin: Note Created & Published

    Note over Student,DownloadRoute: Student attempts download

    Student->>DownloadRoute: Request download for note_id
    DownloadRoute->>NoteService: get_authorized_file(note_id, current_student)
    NoteService->>DB: Query Note by note_id
    NoteService->>NoteService: Check note.class_id == student.class_id
    NoteService->>NoteService: Check note.batch_id is NULL OR note.batch_id == student.batch_id
    alt Unauthorized Class / Batch
        NoteService-->>Student: 403 Forbidden ("You are not enrolled in the class/batch for this material")
    else Authorized
        NoteService->>Disk: Verify file exists on disk
        NoteService-->>Student: Stream FileResponse (media_type, original_filename)
    end
```
