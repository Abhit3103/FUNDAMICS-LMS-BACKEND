import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.security import create_access_token, hash_password
from src.models.academic import Batch, Class, Enrollment, Subject
from src.models.auth_session import AuthSession
from src.models.exam_result import Exam, Result
from src.models.note_file import FileRecord, Note
from src.models.student_attendance import AttendanceStatus, StudentAttendance
from src.models.teacher_attendance import (
    BiometricDevice,
    BiometricEvent,
    BiometricEventType,
    TeacherAttendance,
    TeacherAttendanceStatus,
)
from src.models.user import Student, Teacher, User, UserRole, UserStatus
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5433/fundamics_test",
)

# ---------------------------------------------------------------------------
# Reusable Test Fixtures & Factories
# ---------------------------------------------------------------------------

CREATED_TEMP_FILES = []


def make_auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def create_user(
    db: AsyncSession,
    role: UserRole,
    name: str,
    email: str,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = User(
        role=role,
        name=name,
        email=email,
        password_hash=hash_password("TestSecretPassword123!"),
        status=status,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def create_academic_structure(db: AsyncSession, suffix: str):
    class_obj = Class(
        name=f"Class {suffix}",
        code=f"CLS-{suffix.upper()}-{uuid.uuid4().hex[:6]}",
        academic_year="2026-2027",
        status="ACTIVE",
    )
    db.add(class_obj)
    await db.flush()

    batch_a = Batch(
        class_id=class_obj.id,
        name=f"Batch {suffix}-A",
        code=f"BAT-{suffix.upper()}-A-{uuid.uuid4().hex[:4]}",
        start_time=time(9, 0),
        end_time=time(11, 0),
        status="ACTIVE",
    )
    batch_b = Batch(
        class_id=class_obj.id,
        name=f"Batch {suffix}-B",
        code=f"BAT-{suffix.upper()}-B-{uuid.uuid4().hex[:4]}",
        start_time=time(11, 0),
        end_time=time(13, 0),
        status="ACTIVE",
    )
    db.add_all([batch_a, batch_b])
    await db.flush()

    subject_obj = Subject(
        class_id=class_obj.id,
        name=f"Subject {suffix}",
        code=f"SUB-{suffix.upper()}-{uuid.uuid4().hex[:4]}",
        status="ACTIVE",
    )
    db.add(subject_obj)
    await db.flush()

    return class_obj, batch_a, batch_b, subject_obj


async def create_student_profile(
    db: AsyncSession,
    user: User,
    class_id: uuid.UUID,
    batch_id: uuid.UUID,
    code_suffix: str,
) -> Student:
    student = Student(
        user_id=user.id,
        student_code=f"STU-{code_suffix.upper()}-{uuid.uuid4().hex[:6]}",
        class_id=class_id,
        batch_id=batch_id,
        admission_date=date.today(),
        status="ACTIVE",
    )
    db.add(student)
    await db.flush()

    enrollment = Enrollment(
        student_id=student.id,
        class_id=class_id,
        batch_id=batch_id,
        start_date=date.today(),
        status="ACTIVE",
    )
    db.add(enrollment)
    await db.flush()
    return student


async def create_teacher_profile(
    db: AsyncSession,
    user: User,
    code_suffix: str,
) -> Teacher:
    teacher = Teacher(
        user_id=user.id,
        teacher_code=f"TCH-{code_suffix.upper()}-{uuid.uuid4().hex[:6]}",
        biometric_employee_id=f"EMP-{code_suffix.upper()}-{uuid.uuid4().hex[:4]}",
        status="ACTIVE",
    )
    db.add(teacher)
    await db.flush()
    return teacher


async def create_note_with_file(
    db: AsyncSession,
    class_id: uuid.UUID,
    batch_id: Optional[uuid.UUID],
    subject_id: uuid.UUID,
    creator_id: uuid.UUID,
    title: str,
    status: str = "PUBLISHED",
    file_bytes: bytes = b"%PDF-1.4 test document content",
) -> Note:
    os.makedirs(settings.LOCAL_STORAGE_DIR, exist_ok=True)
    storage_filename = f"test_{uuid.uuid4()}.pdf"
    storage_path = os.path.join(settings.LOCAL_STORAGE_DIR, storage_filename)
    with open(storage_path, "wb") as f:
        f.write(file_bytes)
    CREATED_TEMP_FILES.append(storage_path)

    file_record = FileRecord(
        storage_key=storage_path,
        original_filename="sample_notes.pdf",
        mime_type="application/pdf",
        size_bytes=len(file_bytes),
        checksum="testchecksum12345",
        visibility="PRIVATE",
        created_by=creator_id,
    )
    db.add(file_record)
    await db.flush()

    note = Note(
        title=title,
        description="Test material description",
        class_id=class_id,
        batch_id=batch_id,
        subject_id=subject_id,
        file_id=file_record.id,
        status=status,
        created_by=creator_id,
    )
    db.add(note)
    await db.flush()
    return note


# ---------------------------------------------------------------------------
# Requirement 10: Database Isolation Verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_database_isolation_and_safety(db_session: AsyncSession):
    """Confirm test environment is strictly fundamics_test and not Supabase."""
    assert "supabase" not in TEST_DATABASE_URL.lower(), "SECURITY CRITICAL: Tests must not connect to Supabase!"
    assert "fundamics_test" in TEST_DATABASE_URL.lower(), "SECURITY CRITICAL: Tests must run on fundamics_test!"

    res = await db_session.execute(text("SELECT current_database()"))
    current_db = res.scalar()
    assert current_db == "fundamics_test", f"Expected 'fundamics_test', got '{current_db}'"


# ---------------------------------------------------------------------------
# Requirement 6: Authentication Failures & Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_missing_token(async_client: AsyncClient):
    """Missing bearer token must yield 401 Unauthorized."""
    response = await async_client.get("/api/v1/student/me/attendance/summary")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_auth_malformed_token(async_client: AsyncClient):
    """Malformed bearer token must yield 401 Unauthorized."""
    headers = {"Authorization": "Bearer not.a.valid.jwt.payload"}
    response = await async_client.get("/api/v1/student/me/attendance/summary", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_auth_expired_jwt(async_client: AsyncClient, db_session: AsyncSession):
    """Expired JWT must yield 401 Unauthorized."""
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "exp")
    user = await create_user(db_session, UserRole.STUDENT, "Expired Student", "exp_student@test.local")
    await create_student_profile(db_session, user, class_1.id, batch_1a.id, "exp")

    # Issue expired token (negative expiration delta)
    expired_token = create_access_token(
        str(user.id),
        user.role.value,
        expires_delta=timedelta(seconds=-60),
    )
    headers = make_auth_header(expired_token)
    response = await async_client.get("/api/v1/student/me/attendance/summary", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_auth_nonexistent_user_token(async_client: AsyncClient):
    """Token for deleted or non-existent user must yield 401 Unauthorized."""
    random_user_id = str(uuid.uuid4())
    token = create_access_token(random_user_id, "STUDENT")
    headers = make_auth_header(token)
    response = await async_client.get("/api/v1/student/me/attendance/summary", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_auth_suspended_user_blocked(async_client: AsyncClient, db_session: AsyncSession):
    """Suspended user must receive 403 Forbidden even with valid JWT."""
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "susp")
    user = await create_user(
        db_session,
        UserRole.STUDENT,
        "Suspended Student",
        "suspended_student@test.local",
        status=UserStatus.SUSPENDED,
    )
    await create_student_profile(db_session, user, class_1.id, batch_1a.id, "susp")

    token = create_access_token(str(user.id), user.role.value)
    headers = make_auth_header(token)
    response = await async_client.get("/api/v1/student/me/attendance/summary", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_auth_student_role_without_student_profile(async_client: AsyncClient, db_session: AsyncSession):
    """User with STUDENT role in JWT but missing student profile row must receive 403 Forbidden."""
    user = await create_user(db_session, UserRole.STUDENT, "Orphan Student", "orphan_student@test.local")
    token = create_access_token(str(user.id), user.role.value)
    headers = make_auth_header(token)

    response = await async_client.get("/api/v1/student/me/attendance/summary", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_auth_teacher_role_without_teacher_profile(async_client: AsyncClient, db_session: AsyncSession):
    """User with TEACHER role in JWT but missing teacher profile row must receive 403 Forbidden."""
    user = await create_user(db_session, UserRole.TEACHER, "Orphan Teacher", "orphan_teacher@test.local")
    token = create_access_token(str(user.id), user.role.value)
    headers = make_auth_header(token)

    response = await async_client.get("/api/v1/teacher/me/attendance/summary", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Requirement 3: Student Role Restrictions (Access to Admin & Teacher Operations)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_student_forbidden_on_admin_and_teacher_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Student must receive 403 Forbidden on all administrative and teacher operations."""
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "srest")
    user = await create_user(db_session, UserRole.STUDENT, "Student Restricted", "srest@test.local")
    await create_student_profile(db_session, user, class_1.id, batch_1a.id, "srest")

    token = create_access_token(str(user.id), user.role.value)
    headers = make_auth_header(token)
    fake_uuid = str(uuid.uuid4())

    restricted_endpoints = [
        ("GET", "/api/v1/admin/students", None),
        ("POST", "/api/v1/admin/students", {}),
        ("GET", "/api/v1/admin/teachers", None),
        ("POST", "/api/v1/admin/teachers", {}),
        ("GET", "/api/v1/admin/classes", None),
        ("POST", "/api/v1/admin/classes", {}),
        ("GET", "/api/v1/admin/batches", None),
        ("POST", "/api/v1/admin/batches", {}),
        ("GET", "/api/v1/admin/subjects", None),
        ("POST", "/api/v1/admin/subjects", {}),
        ("POST", "/api/v1/admin/attendance/preview", {}),
        ("POST", f"/api/v1/admin/attendance/confirm/{fake_uuid}", []),
        ("POST", f"/api/v1/admin/teacher-attendance/{fake_uuid}/calculate", None),
        ("POST", "/api/v1/admin/exams", {}),
        ("POST", "/api/v1/admin/exams/marks", {}),
        ("POST", "/api/v1/admin/exams/publish", {}),
        ("POST", "/api/v1/admin/notes", {}),
        ("GET", "/api/v1/admin/calendar/events", None),
        ("POST", "/api/v1/admin/calendar/events", {}),
        ("GET", "/api/v1/admin/settings/institute", None),
        ("PATCH", "/api/v1/admin/settings/institute", {}),
        ("GET", "/api/v1/admin/audit-logs", None),
        # Teacher persona endpoint
        ("GET", "/api/v1/teacher/me/attendance/summary", None),
    ]

    for method, endpoint, payload in restricted_endpoints:
        if method == "GET":
            resp = await async_client.get(endpoint, headers=headers)
        elif method == "POST":
            resp = await async_client.post(endpoint, json=payload, headers=headers)
        elif method == "PATCH":
            resp = await async_client.patch(endpoint, json=payload, headers=headers)

        assert resp.status_code == 403, f"Expected 403 on {method} {endpoint}, got {resp.status_code}"
        assert resp.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Requirement 4: Teacher Role Restrictions (Access to Admin & Student Operations)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_teacher_forbidden_on_admin_and_student_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Teacher must receive 403 Forbidden on all administrative and student operations."""
    user = await create_user(db_session, UserRole.TEACHER, "Teacher Restricted", "trest@test.local")
    await create_teacher_profile(db_session, user, "trest")

    token = create_access_token(str(user.id), user.role.value)
    headers = make_auth_header(token)
    fake_uuid = str(uuid.uuid4())

    restricted_endpoints = [
        ("GET", "/api/v1/admin/students", None),
        ("POST", "/api/v1/admin/students", {}),
        ("GET", "/api/v1/admin/teachers", None),
        ("POST", "/api/v1/admin/teachers", {}),
        ("GET", "/api/v1/admin/classes", None),
        ("POST", "/api/v1/admin/classes", {}),
        ("POST", "/api/v1/admin/exams", {}),
        ("POST", "/api/v1/admin/exams/marks", {}),
        ("POST", "/api/v1/admin/exams/publish", {}),
        ("POST", "/api/v1/admin/notes", {}),
        ("POST", "/api/v1/admin/attendance/preview", {}),
        ("POST", f"/api/v1/admin/attendance/confirm/{fake_uuid}", []),
        ("POST", f"/api/v1/admin/teacher-attendance/{fake_uuid}/calculate", None),
        ("GET", "/api/v1/admin/audit-logs", None),
        ("GET", "/api/v1/admin/settings/institute", None),
        ("PATCH", "/api/v1/admin/settings/institute", {}),
        # Student persona endpoints
        ("GET", "/api/v1/student/me/attendance/summary", None),
        ("GET", "/api/v1/student/me/results", None),
        ("GET", "/api/v1/student/me/notes", None),
        ("GET", f"/api/v1/student/me/notes/{fake_uuid}/download", None),
    ]

    for method, endpoint, payload in restricted_endpoints:
        if method == "GET":
            resp = await async_client.get(endpoint, headers=headers)
        elif method == "POST":
            resp = await async_client.post(endpoint, json=payload, headers=headers)
        elif method == "PATCH":
            resp = await async_client.patch(endpoint, json=payload, headers=headers)

        assert resp.status_code == 403, f"Expected 403 on {method} {endpoint}, got {resp.status_code}"
        assert resp.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Requirement 5: Admin Authorized Operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_authorized_on_administrative_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Admin must succeed on administrative operations."""
    admin_user = await create_user(db_session, UserRole.ADMIN, "System Admin", "sysadmin@test.local")
    token = create_access_token(str(admin_user.id), admin_user.role.value)
    headers = make_auth_header(token)

    # 1. Query students list
    res = await async_client.get("/api/v1/admin/students", headers=headers)
    assert res.status_code == 200

    # 2. Query teachers list
    res = await async_client.get("/api/v1/admin/teachers", headers=headers)
    assert res.status_code == 200

    # 3. Query classes list
    res = await async_client.get("/api/v1/admin/classes", headers=headers)
    assert res.status_code == 200

    # 4. Create a class
    cls_payload = {
        "name": "Grade 12 Advanced",
        "code": f"G12-ADV-{uuid.uuid4().hex[:6]}",
        "academic_year": "2026-2027",
    }
    res = await async_client.post("/api/v1/admin/classes", json=cls_payload, headers=headers)
    assert res.status_code == 201
    assert res.json()["name"] == "Grade 12 Advanced"

    # 5. Query audit logs
    res = await async_client.get("/api/v1/admin/audit-logs", headers=headers)
    assert res.status_code == 200

    # 6. Query institute settings
    res = await async_client.get("/api/v1/admin/settings/institute", headers=headers)
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Requirement 1, 7: Notes Authorization & Cross-Class/Batch IDOR Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notes_authorization_and_idor_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Verify:
    - Student A (Class 1, Batch A) only sees notes for Class 1 (batch-free or Batch A).
    - Student B (Class 1, Batch B) only sees notes for Class 1 (batch-free or Batch B).
    - Student C (Class 2, Batch A) only sees Class 2 notes.
    - Unpublished (Draft) notes are NEVER returned in list.
    - Student A cannot download Student B's batch note -> 403 Forbidden.
    - Student A cannot download Student C's class note -> 403 Forbidden.
    - Student A cannot download an unpublished note -> 404 Not Found.
    - Student A can download authorized notes -> 200 OK with correct content.
    """
    admin = await create_user(db_session, UserRole.ADMIN, "Notes Admin", "notes_admin@test.local")

    # Academic Structure 1: Class 1 with Batch 1A and Batch 1B
    class_1, batch_1a, batch_1b, subject_1 = await create_academic_structure(db_session, "n1")
    # Academic Structure 2: Class 2 with Batch 2A and Batch 2B
    class_2, batch_2a, _, subject_2 = await create_academic_structure(db_session, "n2")

    # Students
    user_a = await create_user(db_session, UserRole.STUDENT, "Student A", "student_a_notes@test.local")
    student_a = await create_student_profile(db_session, user_a, class_1.id, batch_1a.id, "na")

    user_b = await create_user(db_session, UserRole.STUDENT, "Student B", "student_b_notes@test.local")
    student_b = await create_student_profile(db_session, user_b, class_1.id, batch_1b.id, "nb")

    user_c = await create_user(db_session, UserRole.STUDENT, "Student C", "student_c_notes@test.local")
    student_c = await create_student_profile(db_session, user_c, class_2.id, batch_2a.id, "nc")

    token_a = create_access_token(str(user_a.id), user_a.role.value)
    token_b = create_access_token(str(user_b.id), user_b.role.value)
    token_c = create_access_token(str(user_c.id), user_c.role.value)

    # Note 1: Class 1, All Batches (batch_id=None), Published
    note_class1_shared = await create_note_with_file(
        db_session, class_1.id, None, subject_1.id, admin.id,
        title="Class 1 Shared Note", status="PUBLISHED", file_bytes=b"Content: Class 1 Shared",
    )
    # Note 2: Class 1, Batch 1A specific, Published
    note_batch_1a = await create_note_with_file(
        db_session, class_1.id, batch_1a.id, subject_1.id, admin.id,
        title="Batch 1A Exclusive Note", status="PUBLISHED", file_bytes=b"Content: Batch 1A Only",
    )
    # Note 3: Class 1, Batch 1B specific, Published
    note_batch_1b = await create_note_with_file(
        db_session, class_1.id, batch_1b.id, subject_1.id, admin.id,
        title="Batch 1B Exclusive Note", status="PUBLISHED", file_bytes=b"Content: Batch 1B Only",
    )
    # Note 4: Class 2, Batch 2A specific, Published
    note_class2 = await create_note_with_file(
        db_session, class_2.id, batch_2a.id, subject_2.id, admin.id,
        title="Class 2 Exclusive Note", status="PUBLISHED", file_bytes=b"Content: Class 2 Only",
    )
    # Note 5: Class 1, Batch 1A, UNPUBLISHED (status="DRAFT")
    note_draft = await create_note_with_file(
        db_session, class_1.id, batch_1a.id, subject_1.id, admin.id,
        title="Unpublished Draft Note", status="DRAFT", file_bytes=b"Content: Secret Draft",
    )

    # --- Student A Note Listing ---
    res_a = await async_client.get("/api/v1/student/me/notes", headers=make_auth_header(token_a))
    assert res_a.status_code == 200
    notes_a_ids = {n["id"] for n in res_a.json()}
    assert str(note_class1_shared.id) in notes_a_ids, "Student A must see class-wide published note"
    assert str(note_batch_1a.id) in notes_a_ids, "Student A must see Batch 1A note"
    assert str(note_batch_1b.id) not in notes_a_ids, "IDOR VIOLATION: Student A saw Batch 1B note!"
    assert str(note_class2.id) not in notes_a_ids, "IDOR VIOLATION: Student A saw Class 2 note!"
    assert str(note_draft.id) not in notes_a_ids, "SECURITY VIOLATION: Student A saw unpublished note!"

    # --- Student B Note Listing ---
    res_b = await async_client.get("/api/v1/student/me/notes", headers=make_auth_header(token_b))
    assert res_b.status_code == 200
    notes_b_ids = {n["id"] for n in res_b.json()}
    assert str(note_class1_shared.id) in notes_b_ids, "Student B must see class-wide published note"
    assert str(note_batch_1b.id) in notes_b_ids, "Student B must see Batch 1B note"
    assert str(note_batch_1a.id) not in notes_b_ids, "IDOR VIOLATION: Student B saw Batch 1A note!"
    assert str(note_class2.id) not in notes_b_ids, "IDOR VIOLATION: Student B saw Class 2 note!"

    # --- Student C Note Listing ---
    res_c = await async_client.get("/api/v1/student/me/notes", headers=make_auth_header(token_c))
    assert res_c.status_code == 200
    notes_c_ids = {n["id"] for n in res_c.json()}
    assert str(note_class2.id) in notes_c_ids, "Student C must see Class 2 note"
    assert str(note_class1_shared.id) not in notes_c_ids, "IDOR VIOLATION: Student C saw Class 1 note!"
    assert str(note_batch_1a.id) not in notes_c_ids, "IDOR VIOLATION: Student C saw Batch 1A note!"
    assert str(note_batch_1b.id) not in notes_c_ids, "IDOR VIOLATION: Student C saw Batch 1B note!"

    # --- Note Download Authorization & IDOR Checks ---

    # 1. Student A downloads authorized shared note -> 200 OK
    dl_res = await async_client.get(
        f"/api/v1/student/me/notes/{note_class1_shared.id}/download",
        headers=make_auth_header(token_a),
    )
    assert dl_res.status_code == 200
    assert dl_res.content == b"Content: Class 1 Shared"

    # 2. Student A downloads authorized Batch 1A note -> 200 OK
    dl_res = await async_client.get(
        f"/api/v1/student/me/notes/{note_batch_1a.id}/download",
        headers=make_auth_header(token_a),
    )
    assert dl_res.status_code == 200
    assert dl_res.content == b"Content: Batch 1A Only"

    # 3. Student A attempts to download Student B's Batch 1B note -> 403 Forbidden
    dl_b_attempt = await async_client.get(
        f"/api/v1/student/me/notes/{note_batch_1b.id}/download",
        headers=make_auth_header(token_a),
    )
    assert dl_b_attempt.status_code == 403, "IDOR: Student A must be forbidden from downloading Batch 1B note"
    assert dl_b_attempt.json()["error"]["code"] == "FORBIDDEN"

    # 4. Student A attempts to download Class 2 note -> 403 Forbidden
    dl_c_attempt = await async_client.get(
        f"/api/v1/student/me/notes/{note_class2.id}/download",
        headers=make_auth_header(token_a),
    )
    assert dl_c_attempt.status_code == 403, "IDOR: Student A must be forbidden from downloading Class 2 note"
    assert dl_c_attempt.json()["error"]["code"] == "FORBIDDEN"

    # 5. Student A attempts to download draft/unpublished note -> 404 Not Found
    dl_draft_attempt = await async_client.get(
        f"/api/v1/student/me/notes/{note_draft.id}/download",
        headers=make_auth_header(token_a),
    )
    assert dl_draft_attempt.status_code == 404, "SECURITY: Draft/unpublished note must return 404 Not Found"
    assert dl_draft_attempt.json()["error"]["code"] == "NOT_FOUND"

    # 6. Non-existent note -> 404 Not Found
    fake_note_id = str(uuid.uuid4())
    dl_fake = await async_client.get(
        f"/api/v1/student/me/notes/{fake_note_id}/download",
        headers=make_auth_header(token_a),
    )
    assert dl_fake.status_code == 404


# ---------------------------------------------------------------------------
# Requirement 1, 8: Results Authorization & Cross-Student IDOR Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_student_results_ownership_and_idor_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Verify:
    - Student A only sees Student A's published results.
    - Student B's results are NEVER exposed to Student A.
    - Unpublished results are NEVER returned.
    - Parameter tampering (?student_id=...) cannot expose another student's results.
    """
    class_1, batch_1a, _, subject_1 = await create_academic_structure(db_session, "res")

    user_a = await create_user(db_session, UserRole.STUDENT, "Student A", "student_a_res@test.local")
    student_a = await create_student_profile(db_session, user_a, class_1.id, batch_1a.id, "resa")

    user_b = await create_user(db_session, UserRole.STUDENT, "Student B", "student_b_res@test.local")
    student_b = await create_student_profile(db_session, user_b, class_1.id, batch_1a.id, "resb")

    token_a = create_access_token(str(user_a.id), user_a.role.value)
    token_b = create_access_token(str(user_b.id), user_b.role.value)

    # Exam 1: Published
    exam_1 = Exam(
        class_id=class_1.id,
        batch_id=batch_1a.id,
        name="Midterm Examination 2026",
        date=date.today(),
        status="PUBLISHED",
    )
    # Exam 2: Unpublished (Marks entered, but not published)
    exam_2 = Exam(
        class_id=class_1.id,
        batch_id=batch_1a.id,
        name="Surprise Quiz 2026",
        date=date.today(),
        status="MARKS_ENTERED",
    )
    db_session.add_all([exam_1, exam_2])
    await db_session.flush()

    pub_time = datetime.now(timezone.utc)
    # Result for Student A in Exam 1 (Published)
    res_a_exam1 = Result(
        exam_id=exam_1.id,
        student_id=student_a.id,
        subject_id=subject_1.id,
        marks_obtained=88.50,
        max_marks=100.0,
        grade="A+",
        published_at=pub_time,
    )
    # Result for Student B in Exam 1 (Published)
    res_b_exam1 = Result(
        exam_id=exam_1.id,
        student_id=student_b.id,
        subject_id=subject_1.id,
        marks_obtained=45.00,
        max_marks=100.0,
        grade="C",
        published_at=pub_time,
    )
    # Result for Student A in Exam 2 (UNPUBLISHED)
    res_a_exam2 = Result(
        exam_id=exam_2.id,
        student_id=student_a.id,
        subject_id=subject_1.id,
        marks_obtained=99.00,
        max_marks=100.0,
        grade="O",
        published_at=None,
    )
    # Result for Student B in Exam 2 (UNPUBLISHED)
    res_b_exam2 = Result(
        exam_id=exam_2.id,
        student_id=student_b.id,
        subject_id=subject_1.id,
        marks_obtained=60.00,
        max_marks=100.0,
        grade="B",
        published_at=None,
    )
    db_session.add_all([res_a_exam1, res_b_exam1, res_a_exam2, res_b_exam2])
    await db_session.flush()

    # 1. Student A queries results
    response_a = await async_client.get(
        "/api/v1/student/me/results",
        headers=make_auth_header(token_a),
    )
    assert response_a.status_code == 200
    data_a = response_a.json()

    # Must contain only published Exam 1
    exam_names_a = [e["exam_name"] for e in data_a]
    assert "Midterm Examination 2026" in exam_names_a
    assert "Surprise Quiz 2026" not in exam_names_a, "SECURITY: Unpublished exam was returned!"

    # Verify scores returned belong only to Student A
    all_marks_a = [item["marks_obtained"] for e in data_a for item in e["results"]]
    assert 88.5 in all_marks_a, "Student A's published marks must be present"
    assert 45.0 not in all_marks_a, "IDOR: Student B's score of 45.0 was leaked to Student A!"

    # 2. Student B queries results
    response_b = await async_client.get(
        "/api/v1/student/me/results",
        headers=make_auth_header(token_b),
    )
    assert response_b.status_code == 200
    data_b = response_b.json()

    exam_names_b = [e["exam_name"] for e in data_b]
    assert "Midterm Examination 2026" in exam_names_b
    assert "Surprise Quiz 2026" not in exam_names_b, "SECURITY: Unpublished exam was returned!"

    all_marks_b = [item["marks_obtained"] for e in data_b for item in e["results"]]
    assert 45.0 in all_marks_b, "Student B's published marks must be present"
    assert 88.5 not in all_marks_b, "IDOR: Student A's score of 88.5 was leaked to Student B!"

    # 3. Parameter tampering attempt: Student A passes Student B's student_id
    tampered_response = await async_client.get(
        f"/api/v1/student/me/results?student_id={student_b.id}",
        headers=make_auth_header(token_a),
    )
    assert tampered_response.status_code == 200
    tampered_data = tampered_response.json()
    tampered_marks = [item["marks_obtained"] for e in tampered_data for item in e["results"]]
    assert 88.5 in tampered_marks
    assert 45.0 not in tampered_marks, "IDOR: Parameter tampering leaked Student B's marks!"


# ---------------------------------------------------------------------------
# Requirement 1, 9: Student Attendance Ownership & IDOR Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_student_attendance_ownership_and_idor_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Verify:
    - Student A's summary reflects ONLY Student A's attendance records.
    - Student B's attendance records do NOT alter or leak into Student A's summary.
    - Parameter tampering (?student_id=...) cannot affect authenticated student's output.
    """
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "att")

    user_a = await create_user(db_session, UserRole.STUDENT, "Student A Att", "student_a_att@test.local")
    student_a = await create_student_profile(db_session, user_a, class_1.id, batch_1a.id, "atta")

    user_b = await create_user(db_session, UserRole.STUDENT, "Student B Att", "student_b_att@test.local")
    student_b = await create_student_profile(db_session, user_b, class_1.id, batch_1a.id, "attb")

    token_a = create_access_token(str(user_a.id), user_a.role.value)
    token_b = create_access_token(str(user_b.id), user_b.role.value)

    # Student A: 3 PRESENT, 1 ABSENT -> 4 total, 75.0%
    dates_a = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)]
    statuses_a = [AttendanceStatus.PRESENT, AttendanceStatus.PRESENT, AttendanceStatus.PRESENT, AttendanceStatus.ABSENT]
    for d, s in zip(dates_a, statuses_a):
        db_session.add(
            StudentAttendance(
                student_id=student_a.id,
                class_id=class_1.id,
                batch_id=batch_1a.id,
                date=d,
                status=s,
                source="TEST",
            )
        )

    # Student B: 5 PRESENT, 0 ABSENT -> 5 total, 100.0%
    dates_b = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4), date(2026, 9, 5)]
    for d in dates_b:
        db_session.add(
            StudentAttendance(
                student_id=student_b.id,
                class_id=class_1.id,
                batch_id=batch_1a.id,
                date=d,
                status=AttendanceStatus.PRESENT,
                source="TEST",
            )
        )
    await db_session.flush()

    # 1. Student A summary
    resp_a = await async_client.get(
        "/api/v1/student/me/attendance/summary",
        headers=make_auth_header(token_a),
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["student_id"] == str(student_a.id)
    assert data_a["total_working_days"] == 4
    assert data_a["present_days"] == 3
    assert data_a["absent_days"] == 1
    assert data_a["attendance_percentage"] == 75.0

    # 2. Student B summary
    resp_b = await async_client.get(
        "/api/v1/student/me/attendance/summary",
        headers=make_auth_header(token_b),
    )
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["student_id"] == str(student_b.id)
    assert data_b["total_working_days"] == 5
    assert data_b["present_days"] == 5
    assert data_b["absent_days"] == 0
    assert data_b["attendance_percentage"] == 100.0

    # 3. Parameter tampering attempt: Student A passes Student B's student_id
    resp_tamper = await async_client.get(
        f"/api/v1/student/me/attendance/summary?student_id={student_b.id}",
        headers=make_auth_header(token_a),
    )
    assert resp_tamper.status_code == 200
    data_tamper = resp_tamper.json()
    assert data_tamper["student_id"] == str(student_a.id), "IDOR: Query parameter overridden authenticated student!"
    assert data_tamper["total_working_days"] == 4
    assert data_tamper["attendance_percentage"] == 75.0


# ---------------------------------------------------------------------------
# Requirement 2: Teacher Ownership & Read-Only Enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_teacher_ownership_and_read_only(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Verify:
    - Teacher A can access only Teacher A's attendance summary.
    - Teacher B's records are NOT included in Teacher A's summary.
    - Parameter tampering (?teacher_id=...) cannot access another teacher's data.
    - Teacher cannot modify attendance records or calculate attendance.
    """
    user_ta = await create_user(db_session, UserRole.TEACHER, "Teacher Alpha", "teacher_a@test.local")
    teacher_a = await create_teacher_profile(db_session, user_ta, "ta")

    user_tb = await create_user(db_session, UserRole.TEACHER, "Teacher Beta", "teacher_b@test.local")
    teacher_b = await create_teacher_profile(db_session, user_tb, "tb")

    token_ta = create_access_token(str(user_ta.id), user_ta.role.value)
    token_tb = create_access_token(str(user_tb.id), user_tb.role.value)

    # Teacher A: 2 days, 10 hours served (600 minutes)
    att_a1 = TeacherAttendance(
        teacher_id=teacher_a.id,
        date=date(2026, 9, 10),
        served_minutes=300,
        required_minutes=480,
        status=TeacherAttendanceStatus.HALF_DAY,
    )
    att_a2 = TeacherAttendance(
        teacher_id=teacher_a.id,
        date=date(2026, 9, 11),
        served_minutes=300,
        required_minutes=480,
        status=TeacherAttendanceStatus.HALF_DAY,
    )
    # Teacher B: 3 days, 24 hours served (1440 minutes)
    att_b1 = TeacherAttendance(
        teacher_id=teacher_b.id,
        date=date(2026, 9, 10),
        served_minutes=480,
        required_minutes=480,
        status=TeacherAttendanceStatus.PRESENT,
    )
    att_b2 = TeacherAttendance(
        teacher_id=teacher_b.id,
        date=date(2026, 9, 11),
        served_minutes=480,
        required_minutes=480,
        status=TeacherAttendanceStatus.PRESENT,
    )
    att_b3 = TeacherAttendance(
        teacher_id=teacher_b.id,
        date=date(2026, 9, 12),
        served_minutes=480,
        required_minutes=480,
        status=TeacherAttendanceStatus.PRESENT,
    )
    db_session.add_all([att_a1, att_a2, att_b1, att_b2, att_b3])
    await db_session.flush()

    # 1. Teacher A queries summary
    res_ta = await async_client.get(
        "/api/v1/teacher/me/attendance/summary",
        headers=make_auth_header(token_ta),
    )
    assert res_ta.status_code == 200
    data_ta = res_ta.json()
    assert data_ta["teacher_id"] == str(teacher_a.id)
    assert data_ta["total_days"] == 2
    assert data_ta["half_days"] == 2
    assert data_ta["present_days"] == 0
    assert data_ta["total_served_hours"] == 10.0

    # 2. Teacher B queries summary
    res_tb = await async_client.get(
        "/api/v1/teacher/me/attendance/summary",
        headers=make_auth_header(token_tb),
    )
    assert res_tb.status_code == 200
    data_tb = res_tb.json()
    assert data_tb["teacher_id"] == str(teacher_b.id)
    assert data_tb["total_days"] == 3
    assert data_tb["present_days"] == 3
    assert data_tb["half_days"] == 0
    assert data_tb["total_served_hours"] == 24.0

    # 3. Parameter tampering: Teacher A passes Teacher B's id
    res_tamper = await async_client.get(
        f"/api/v1/teacher/me/attendance/summary?teacher_id={teacher_b.id}",
        headers=make_auth_header(token_ta),
    )
    assert res_tamper.status_code == 200
    assert res_tamper.json()["teacher_id"] == str(teacher_a.id)
    assert res_tamper.json()["total_served_hours"] == 10.0

    # 4. Teacher attempting mutation: calculation trigger -> 403 Forbidden
    res_mutate = await async_client.post(
        f"/api/v1/admin/teacher-attendance/{teacher_b.id}/calculate?target_date=2026-09-10",
        headers=make_auth_header(token_ta),
    )
    assert res_mutate.status_code == 403
    assert res_mutate.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# Requirement 1: JWT Session Tracking & Revocation Lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jwt_session_full_lifecycle(async_client: AsyncClient, db_session: AsyncSession):
    """
    Verify:
    A. Normal login issues JWT containing session_id.
    B. Valid authenticated session can access protected endpoints.
    C. Calling /logout revokes the session in the database.
    D. Revoked session token cannot access protected endpoints (401 Unauthorized).
    E. Refresh token for revoked session is rejected (401 Unauthorized).
    """
    # 1. Create active user with known credentials
    password = "UserSecretPassword123!"
    user = User(
        role=UserRole.STUDENT,
        name="Session Test Student",
        email="session_student@example.com",
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "sess")
    await create_student_profile(db_session, user, class_1.id, batch_1a.id, "sess")

    # 2. Login via API
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Verify session_id claim in JWT
    from src.core.security import decode_access_token
    claims = decode_access_token(access_token)
    assert "session_id" in claims, "SECURITY: Access token must contain session_id claim!"
    session_id = claims["session_id"]

    # 3. Access protected endpoint -> 200 OK
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers=make_auth_header(access_token),
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == user.email

    # 4. Logout via API -> 200 OK
    logout_resp = await async_client.post(
        "/api/v1/auth/logout",
        headers=make_auth_header(access_token),
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True

    # Verify in DB that session was revoked
    sess_stmt = select(AuthSession).where(AuthSession.id == uuid.UUID(session_id))
    sess_res = await db_session.execute(sess_stmt)
    db_sess = sess_res.scalar_one_or_none()
    assert db_sess is not None
    assert db_sess.revoked_at is not None, "SECURITY: Logout must set revoked_at on the session!"

    # 5. Attempt protected access with the revoked access token -> 401 Unauthorized
    revoked_access_resp = await async_client.get(
        "/api/v1/auth/me",
        headers=make_auth_header(access_token),
    )
    assert revoked_access_resp.status_code == 401
    assert revoked_access_resp.json()["error"]["message"] == "Session has been revoked or expired"

    # 6. Attempt refresh with refresh token of revoked session -> 401 Unauthorized
    refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401
    assert refresh_resp.json()["error"]["message"] == "Refresh token has expired or is invalid"


@pytest.mark.asyncio
async def test_jwt_refresh_rotation_and_revocation(async_client: AsyncClient, db_session: AsyncSession):
    """Verify refresh token rotation and revocation of previous refresh token."""
    password = "UserSecretPassword123!"
    user = User(
        role=UserRole.ADMIN,
        name="Refresh Test Admin",
        email="refresh_admin@example.com",
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    # Login
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    tokens = login_resp.json()
    first_refresh = tokens["refresh_token"]

    # Rotate
    rotate_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert rotate_resp.status_code == 200
    rotated_tokens = rotate_resp.json()
    new_access = rotated_tokens["access_token"]
    second_refresh = rotated_tokens["refresh_token"]
    assert second_refresh != first_refresh

    # Using old refresh token must now fail
    replay_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert replay_resp.status_code == 401

    # New access token works
    me_resp = await async_client.get("/api/v1/auth/me", headers=make_auth_header(new_access))
    assert me_resp.status_code == 200


@pytest.mark.asyncio
async def test_suspended_user_login_attempt(async_client: AsyncClient, db_session: AsyncSession):
    """Suspended user cannot login."""
    password = "UserSecretPassword123!"
    user = User(
        role=UserRole.STUDENT,
        name="Suspended Login Student",
        email="suspended_login@example.com",
        password_hash=hash_password(password),
        status=UserStatus.SUSPENDED,
    )
    db_session.add(user)
    await db_session.flush()

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert login_resp.status_code == 401
    assert "SUSPENDED" in login_resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Requirement 2: Secureye Biometric Webhook Security
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_secureye_missing_device_secret_header(async_client: AsyncClient):
    """Webhook call without x_device_secret header is rejected with 422."""
    payload = [{
        "device_id": "DEV-001",
        "external_event_id": "EVT-100",
        "employee_identifier": "EMP-001",
        "event_type": "IN",
        "event_at_utc": "2026-09-30T09:00:00Z",
    }]
    resp = await async_client.post("/api/v1/integrations/biometric/secureye/events", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_secureye_invalid_device_secret(async_client: AsyncClient):
    """Webhook call with unknown secret is rejected with 401."""
    payload = [{
        "device_id": "DEV-001",
        "external_event_id": "EVT-100",
        "employee_identifier": "EMP-001",
        "event_type": "IN",
        "event_at_utc": "2026-09-30T09:00:00Z",
    }]
    headers = {"x-device-secret": "completely-invalid-secret-key"}
    resp = await async_client.post("/api/v1/integrations/biometric/secureye/events", json=payload, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["message"] == "Invalid device credentials or device inactive"


@pytest.mark.asyncio
async def test_secureye_inactive_device_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """Device marked INACTIVE is rejected even with matching secret."""
    device = BiometricDevice(
        external_device_id="DEV-INACTIVE-01",
        name="Inactive Gate 1",
        secret_reference="inactive-secret-xyz",
        status="INACTIVE",
    )
    db_session.add(device)
    await db_session.flush()

    payload = [{
        "device_id": "DEV-INACTIVE-01",
        "external_event_id": "EVT-101",
        "employee_identifier": "EMP-001",
        "event_type": "IN",
        "event_at_utc": "2026-09-30T09:00:00Z",
    }]
    headers = {"x-device-secret": "inactive-secret-xyz"}
    resp = await async_client.post("/api/v1/integrations/biometric/secureye/events", json=payload, headers=headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_secureye_valid_ingest_and_deduplication(async_client: AsyncClient, db_session: AsyncSession):
    """
    Verify:
    C. Valid device authentication succeeds.
    D/E/F. Duplicate external event IDs are idempotently skipped (replay protection).
    G/H. Secrets are not returned in responses or audit logs.
    """
    secret = "secureye_shared_secret_test_2026"
    device = BiometricDevice(
        external_device_id=f"DEV-ACT-{uuid.uuid4().hex[:6]}",
        name="Main Entrance Device",
        secret_reference=secret,
        status="ACTIVE",
    )
    db_session.add(device)

    # Create teacher with biometric mapping
    t_user = await create_user(db_session, UserRole.TEACHER, "Bio Teacher", "bio_teacher@test.local")
    teacher = await create_teacher_profile(db_session, t_user, "bio")
    await db_session.flush()

    events_payload = [
        {
            "device_id": device.external_device_id,
            "external_event_id": "EVT-SEC-001",
            "employee_identifier": teacher.biometric_employee_id,
            "event_type": "IN",
            "event_at_utc": "2026-09-30T08:55:00Z",
        },
        {
            "device_id": device.external_device_id,
            "external_event_id": "EVT-SEC-002",
            "employee_identifier": teacher.biometric_employee_id,
            "event_type": "OUT",
            "event_at_utc": "2026-09-30T17:05:00Z",
        },
    ]

    headers = {"x-device-secret": secret}
    # 1. First ingestion
    resp1 = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=events_payload,
        headers=headers,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["processed"] == 2
    assert data1["duplicates_skipped"] == 0
    assert "secret" not in str(data1).lower()

    # 2. Second ingestion of SAME events (replay attack simulation)
    resp2 = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=events_payload,
        headers=headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["processed"] == 0
    assert data2["duplicates_skipped"] == 2

    # 3. Verify exactly 2 records in DB
    ev_res = await db_session.execute(
        select(BiometricEvent).where(BiometricEvent.device_id == device.id)
    )
    all_events = ev_res.scalars().all()
    assert len(all_events) == 2


@pytest.mark.asyncio
async def test_secureye_malformed_payload(async_client: AsyncClient, db_session: AsyncSession):
    """Malformed biometric payload is rejected safely with 422."""
    secret = "secret-malformed-test"
    device = BiometricDevice(
        external_device_id=f"DEV-MAL-{uuid.uuid4().hex[:6]}",
        name="Malformed Test Gate",
        secret_reference=secret,
        status="ACTIVE",
    )
    db_session.add(device)
    await db_session.flush()

    headers = {"x-device-secret": secret}
    # Invalid event_type
    bad_payload = [{
        "device_id": device.external_device_id,
        "external_event_id": "EVT-ERR-1",
        "employee_identifier": "EMP-001",
        "event_type": "INVALID_TYPE",
        "event_at_utc": "2026-09-30T09:00:00Z",
    }]
    resp = await async_client.post("/api/v1/integrations/biometric/secureye/events", json=bad_payload, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Requirement 3: Private Storage & Route Exposure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unauthenticated_file_download_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """Unauthenticated users cannot download notes/files."""
    fake_note_id = str(uuid.uuid4())
    resp = await async_client.get(f"/api/v1/student/me/notes/{fake_note_id}/download")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_static_route_for_storage(async_client: AsyncClient):
    """Private storage directory ./storage/notes is NOT mounted as static files."""
    assert (await async_client.get("/storage/notes/test.pdf")).status_code == 404
    assert (await async_client.get("/api/v1/storage/notes/test.pdf")).status_code == 404
    assert (await async_client.get("/notes/test.pdf")).status_code == 404


@pytest.mark.asyncio
async def test_path_traversal_on_note_download(async_client: AsyncClient, db_session: AsyncSession):
    """Path traversal attempts on note download are rejected by route UUID validation."""
    user = await create_user(db_session, UserRole.STUDENT, "PT Student", "pt_student@test.local")
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "pt")
    await create_student_profile(db_session, user, class_1.id, batch_1a.id, "pt")
    token = create_access_token(str(user.id), user.role.value)

    resp = await async_client.get(
        "/api/v1/student/me/notes/../../etc/passwd/download",
        headers=make_auth_header(token),
    )
    assert resp.status_code in [404, 422]


# ---------------------------------------------------------------------------
# Requirement 4: Security Headers & Middleware
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_and_request_id_middleware(async_client: AsyncClient):
    """Verify security headers and X-Request-ID propagation."""
    custom_trace_id = "trace_abc_123_test"
    resp = await async_client.get(
        "/api/v1/health/live",
        headers={"X-Request-ID": custom_trace_id},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_trace_id
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "X-Process-Time" in resp.headers


@pytest.mark.asyncio
async def test_error_response_no_information_disclosure(async_client: AsyncClient):
    """Error responses must not disclose stack traces, secrets, or database URLs."""
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword!"},
    )
    assert resp.status_code == 401
    body = resp.text
    assert "postgres" not in body.lower()
    assert "password" not in body.lower() or "invalid email or password" in body.lower()
    assert "traceback" not in body.lower()
    assert "trace" not in body.lower() or "x-request-id" in resp.headers


# ---------------------------------------------------------------------------
# Requirement 5: Attendance Excel Upload Pipeline Security
# ---------------------------------------------------------------------------

import openpyxl
import io


def build_excel_bytes(headers: list, rows: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_excel_upload_valid_workbook_preview_and_confirm(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Verify:
    A. Valid workbook passes validation.
    L. Preview does NOT commit final attendance.
    M. Confirm performs atomic database commit.
    """
    admin = await create_user(db_session, UserRole.ADMIN, "Import Admin", "import_admin@test.local")
    admin_token = create_access_token(str(admin.id), admin.role.value)
    admin_headers = make_auth_header(admin_token)

    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "xlv")
    user1 = await create_user(db_session, UserRole.STUDENT, "Excel S1", "xl_s1@test.local")
    s1 = await create_student_profile(db_session, user1, class_1.id, batch_1a.id, "xls1")
    user2 = await create_user(db_session, UserRole.STUDENT, "Excel S2", "xl_s2@test.local")
    s2 = await create_student_profile(db_session, user2, class_1.id, batch_1a.id, "xls2")

    excel_bytes = build_excel_bytes(
        headers=["student_code", "status", "remarks"],
        rows=[
            [s1.student_code, "PRESENT", "On time"],
            [s2.student_code, "LATE", "Bus delayed"],
        ],
    )

    # 1. Preview
    files = {"file": ("attendance_valid.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {
        "class_id": str(class_1.id),
        "batch_id": str(batch_1a.id),
        "attendance_date": "2026-10-01",
    }
    preview_resp = await async_client.post(
        "/api/v1/admin/attendance/preview",
        data=data,
        files=files,
        headers=admin_headers,
    )
    assert preview_resp.status_code == 200
    pdata = preview_resp.json()
    assert pdata["total_rows"] == 2
    assert pdata["valid_rows"] == 2
    assert pdata["error_rows"] == 0
    assert pdata["preview_data"][0]["is_valid"] is True
    assert pdata["preview_data"][1]["is_valid"] is True
    import_id = pdata["import_id"]

    # Verify preview did NOT commit attendance records
    att_res = await db_session.execute(
        select(StudentAttendance).where(StudentAttendance.class_id == class_1.id)
    )
    assert len(att_res.scalars().all()) == 0, "SECURITY: Preview must NOT commit attendance to database!"

    # 2. Confirm
    confirm_payload = [
        {"student_code": s1.student_code, "status": "PRESENT", "remarks": "On time"},
        {"student_code": s2.student_code, "status": "LATE", "remarks": "Bus delayed"},
    ]
    confirm_resp = await async_client.post(
        f"/api/v1/admin/attendance/confirm/{import_id}",
        json=confirm_payload,
        headers=admin_headers,
    )
    assert confirm_resp.status_code == 200
    cdata = confirm_resp.json()
    assert cdata["committed_rows"] == 2
    assert cdata["status"] == "COMPLETED"

    # Verify records now committed
    att_res2 = await db_session.execute(
        select(StudentAttendance).where(StudentAttendance.class_id == class_1.id)
    )
    assert len(att_res2.scalars().all()) == 2

    # Double-confirm must fail with 409 Conflict
    reconfirm_resp = await async_client.post(
        f"/api/v1/admin/attendance/confirm/{import_id}",
        json=confirm_payload,
        headers=admin_headers,
    )
    assert reconfirm_resp.status_code == 409


@pytest.mark.asyncio
async def test_excel_upload_invalid_file_type(async_client: AsyncClient, db_session: AsyncSession):
    """Uploading non-.xlsx file is rejected with 422."""
    admin = await create_user(db_session, UserRole.ADMIN, "Admin IFT", "admin_ift@test.local")
    admin_headers = make_auth_header(create_access_token(str(admin.id), admin.role.value))
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "ift")

    files = {"file": ("attendance.csv", b"student_code,status\nS1,PRESENT", "text/csv")}
    data = {
        "class_id": str(class_1.id),
        "batch_id": str(batch_1a.id),
        "attendance_date": "2026-10-01",
    }
    resp = await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=admin_headers)
    assert resp.status_code == 422
    assert "Only .xlsx files are supported" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_excel_upload_oversized_file(async_client: AsyncClient, db_session: AsyncSession):
    """Uploading oversized file (>10MB) is rejected with 422."""
    admin = await create_user(db_session, UserRole.ADMIN, "Admin OS", "admin_os@test.local")
    admin_headers = make_auth_header(create_access_token(str(admin.id), admin.role.value))
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "os")

    huge_bytes = b"0" * (11 * 1024 * 1024)
    files = {"file": ("huge_attendance.xlsx", huge_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {
        "class_id": str(class_1.id),
        "batch_id": str(batch_1a.id),
        "attendance_date": "2026-10-01",
    }
    resp = await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=admin_headers)
    assert resp.status_code == 422
    assert "exceeds maximum allowed limit" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_excel_upload_missing_required_columns(async_client: AsyncClient, db_session: AsyncSession):
    """Workbook missing required columns is rejected with 422."""
    admin = await create_user(db_session, UserRole.ADMIN, "Admin MRC", "admin_mrc@test.local")
    admin_headers = make_auth_header(create_access_token(str(admin.id), admin.role.value))
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "mrc")

    bad_excel = build_excel_bytes(
        headers=["name", "comment"],
        rows=[["John Doe", "Attended"]],
    )
    files = {"file": ("bad_headers.xlsx", bad_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {
        "class_id": str(class_1.id),
        "batch_id": str(batch_1a.id),
        "attendance_date": "2026-10-01",
    }
    resp = await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=admin_headers)
    assert resp.status_code == 422
    assert "Missing required column(s)" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_excel_upload_malformed_workbook(async_client: AsyncClient, db_session: AsyncSession):
    """Corrupted/garbage bytes named .xlsx are rejected with 422."""
    admin = await create_user(db_session, UserRole.ADMIN, "Admin MW", "admin_mw@test.local")
    admin_headers = make_auth_header(create_access_token(str(admin.id), admin.role.value))
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "mw")

    corrupt_bytes = b"NOT_A_VALID_ZIP_OR_EXCEL_STREAM"
    files = {"file": ("corrupt.xlsx", corrupt_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {
        "class_id": str(class_1.id),
        "batch_id": str(batch_1a.id),
        "attendance_date": "2026-10-01",
    }
    resp = await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=admin_headers)
    assert resp.status_code == 422
    assert "Malformed or corrupted Excel workbook" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_excel_upload_validation_errors(async_client: AsyncClient, db_session: AsyncSession):
    """
    Verify row-level validations:
    E. Invalid student code (not enrolled).
    G. Invalid status.
    I. Duplicate student rows.
    J. Conflicting existing attendance.
    """
    admin = await create_user(db_session, UserRole.ADMIN, "Admin VErr", "admin_verr@test.local")
    admin_headers = make_auth_header(create_access_token(str(admin.id), admin.role.value))
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "verr")

    user_enrolled = await create_user(db_session, UserRole.STUDENT, "Enrolled S1", "enrolled_s1@test.local")
    s_enrolled = await create_student_profile(db_session, user_enrolled, class_1.id, batch_1a.id, "enr")

    user_conflict = await create_user(db_session, UserRole.STUDENT, "Conflict S2", "conflict_s2@test.local")
    s_conflict = await create_student_profile(db_session, user_conflict, class_1.id, batch_1a.id, "cnf")

    att_date = date(2026, 10, 15)
    # Pre-record attendance for s_conflict on att_date
    db_session.add(
        StudentAttendance(
            student_id=s_conflict.id,
            class_id=class_1.id,
            batch_id=batch_1a.id,
            date=att_date,
            status=AttendanceStatus.PRESENT,
            source="PRIOR",
        )
    )
    await db_session.flush()

    excel_bytes = build_excel_bytes(
        headers=["student_code", "status", "remarks"],
        rows=[
            ["UNKNOWN_STUDENT_CODE", "PRESENT", "Not enrolled"],
            [s_enrolled.student_code, "INVALID_STATUS_VALUE", "Bad status"],
            [s_enrolled.student_code, "PRESENT", "Duplicate 1"],
            [s_enrolled.student_code, "PRESENT", "Duplicate 2"],
            [s_conflict.student_code, "PRESENT", "Conflict row"],
        ],
    )

    files = {"file": ("errors_attendance.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {
        "class_id": str(class_1.id),
        "batch_id": str(batch_1a.id),
        "attendance_date": str(att_date),
    }
    resp = await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=admin_headers)
    assert resp.status_code == 200
    pdata = resp.json()

    assert pdata["error_rows"] == 5
    assert pdata["valid_rows"] == 0
    err_msgs = [r["error_message"] for r in pdata["preview_data"] if not r["is_valid"]]

    assert any("not enrolled in this class/batch" in m for m in err_msgs)
    assert any("Invalid status" in m for m in err_msgs)
    assert any("Duplicate student code in submission" in m for m in err_msgs)
    assert any("Attendance already recorded" in m for m in err_msgs)


@pytest.mark.asyncio
async def test_excel_upload_invalid_class_or_batch(async_client: AsyncClient, db_session: AsyncSession):
    """Mismatch between class and batch yields 422."""
    admin = await create_user(db_session, UserRole.ADMIN, "Admin CB", "admin_cb@test.local")
    admin_headers = make_auth_header(create_access_token(str(admin.id), admin.role.value))

    class_1, _, _, _ = await create_academic_structure(db_session, "cb1")
    class_2, batch_2a, _, _ = await create_academic_structure(db_session, "cb2")

    excel_bytes = build_excel_bytes(["student_code", "status"], [["S001", "PRESENT"]])
    files = {"file": ("test.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {
        "class_id": str(class_1.id),
        "batch_id": str(batch_2a.id),  # Belongs to class_2!
        "attendance_date": "2026-10-01",
    }
    resp = await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=admin_headers)
    assert resp.status_code == 422
    assert "Batch does not belong to the selected class" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_excel_upload_unauthorized_roles_forbidden(async_client: AsyncClient, db_session: AsyncSession):
    """Students and teachers are forbidden from attendance upload operations."""
    student_u = await create_user(db_session, UserRole.STUDENT, "Student Imp", "student_imp@test.local")
    class_1, batch_1a, _, _ = await create_academic_structure(db_session, "uimp")
    await create_student_profile(db_session, student_u, class_1.id, batch_1a.id, "uimp")
    s_headers = make_auth_header(create_access_token(str(student_u.id), student_u.role.value))

    teacher_u = await create_user(db_session, UserRole.TEACHER, "Teacher Imp", "teacher_imp@test.local")
    await create_teacher_profile(db_session, teacher_u, "uimp")
    t_headers = make_auth_header(create_access_token(str(teacher_u.id), teacher_u.role.value))

    excel_bytes = build_excel_bytes(["student_code", "status"], [["S001", "PRESENT"]])
    files = {"file": ("test.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"class_id": str(class_1.id), "batch_id": str(batch_1a.id), "attendance_date": "2026-10-01"}

    # Student preview -> 403
    assert (await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=s_headers)).status_code == 403
    # Teacher preview -> 403
    assert (await async_client.post("/api/v1/admin/attendance/preview", data=data, files=files, headers=t_headers)).status_code == 403

    # Student confirm -> 403
    fake_import = str(uuid.uuid4())
    assert (await async_client.post(f"/api/v1/admin/attendance/confirm/{fake_import}", json=[], headers=s_headers)).status_code == 403
    # Teacher confirm -> 403
    assert (await async_client.post(f"/api/v1/admin/attendance/confirm/{fake_import}", json=[], headers=t_headers)).status_code == 403


# ---------------------------------------------------------------------------
# Cleanup Fixture for Created Files
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_storage_files():
    yield
    for fpath in CREATED_TEMP_FILES:
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
        except OSError:
            pass
