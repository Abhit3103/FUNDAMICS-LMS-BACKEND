# Coaching Centre LMS - Logical ERD V1.2

## RBAC
- ADMIN: full operational access.
- TEACHER: read-only own attendance + attendance analytics.
- STUDENT: read-only own published results + class/batch-assigned notes.

## Relationships
```text
users 1──1 students
users 1──1 teachers
classes 1──N batches
classes 1──N subjects
students 1──N enrollments N──1 batches
students 1──N student_attendance N──1 attendance_imports
teachers 1──N biometric_events N──1 biometric_devices
teachers 1──N teacher_attendance
classes 1──N exams 1──N results N──1 students
subjects 1──N results
classes 1──N notes N──1 subjects; notes -> files
users 1──N audit_logs
users 1──N auth_sessions

### users
- id PK
- role
- name
- email UNIQUE
- phone
- password_hash
- status
- email_verified_at
- created_at
- updated_at

### students
- id PK
- user_id UNIQUE FK
- student_code UNIQUE
- class_id FK
- batch_id FK
- admission_date
- status

### teachers
- id PK
- user_id UNIQUE FK
- teacher_code UNIQUE
- biometric_employee_id UNIQUE NULL
- status

### classes
- id PK
- name
- code UNIQUE
- academic_year
- status

### batches
- id PK
- class_id FK
- name
- code
- start_time
- end_time
- status
- UNIQUE(class_id,code)

### subjects
- id PK
- class_id FK
- name
- code
- status
- UNIQUE(class_id,code)

### enrollments
- id PK
- student_id FK
- class_id FK
- batch_id FK
- start_date
- end_date NULL
- status

### student_attendance
- id PK
- student_id FK
- class_id FK
- batch_id FK
- date
- status
- remarks
- source
- import_id NULL
- created_at
- updated_at
- UNIQUE(student_id,date)

### attendance_imports
- id PK
- uploaded_by FK
- class_id
- batch_id
- from_date
- to_date
- filename
- status
- total_rows
- valid_rows
- error_rows
- created_at
- completed_at

### biometric_devices
- id PK
- external_device_id UNIQUE
- name
- model
- secret_reference
- status
- last_seen_at

### biometric_events
- id PK
- device_id FK
- external_event_id
- employee_identifier
- teacher_id NULL FK
- event_type
- event_at_utc
- raw_reference
- received_at
- UNIQUE(device_id,external_event_id)

### teacher_attendance
- id PK
- teacher_id FK
- date
- check_in_at
- check_out_at
- served_minutes
- required_minutes
- status
- calculation_version
- source
- created_at
- updated_at
- UNIQUE(teacher_id,date)

### exams
- id PK
- class_id FK
- batch_id NULL FK
- name
- date
- status

### results
- id PK
- exam_id FK
- student_id FK
- subject_id FK
- marks_obtained
- max_marks
- grade
- published_at
- UNIQUE(exam_id,student_id,subject_id)

### files
- id PK
- storage_key
- original_filename
- mime_type
- size_bytes
- checksum
- visibility PRIVATE
- created_by FK
- created_at

### notes
- id PK
- title
- description
- class_id FK
- batch_id NULL FK
- subject_id FK
- file_id FK
- status
- created_by FK
- created_at
- updated_at

### academic_calendar_events
- id PK
- title
- date
- type
- applies_to
- class_id NULL
- batch_id NULL
- created_by FK

### notification_records
- id PK
- event_type
- recipient_reference
- channel/provider
- status
- payload_reference
- created_at
- sent_at
- failure_code

### audit_logs
- id PK
- actor_id FK
- action
- resource_type
- resource_id
- before_json
- after_json
- request_id
- created_at

### institute_settings
- id PK singleton
- status
- attendance_required_hours
- timezone
- attendance_cutoff_time
- missing_checkout_policy
- notifications_enabled
- updated_by FK
- updated_at

### auth_sessions
- id PK
- user_id FK
- refresh_token_hash
- device_reference
- expires_at
- revoked_at
- created_at

### verification_tokens
- id PK
- user_id FK
- token_hash
- expires_at
- used_at

### password_reset_tokens
- id PK
- user_id FK
- token_hash
- expires_at
- used_at


## V1 student attendance access

Students have read-only access to their own attendance records and attendance analytics/summary.
Analytics may include working days, present days, absent days, late days, excused days, attendance percentage, and subject-wise breakdowns where applicable. A student must never be able to query another student's attendance.

## V1 result scope

The Results module does not conduct exams. It stores academic result/marks data that Admin enters or uploads and publishes. Online exam-taking is deferred to a future version.
