import os
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.academic import Batch, Class, Enrollment, Subject
from src.models.student_attendance import AttendanceStatus, StudentAttendance
from src.models.system import AcademicCalendarEvent, CalendarEventType, AuditLog
from src.models.user import Student, User, UserRole, UserStatus


def make_auth_header(user: User) -> dict:
    token = create_access_token(subject=str(user.id), role=user.role.value)
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
        password_hash=hash_password("TestSecretPass123!"),
        status=status,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()
    return user


async def create_academic_setup(db: AsyncSession, suffix: str):
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
    other_class = Class(
        name=f"Other Class {suffix}",
        code=f"CLS-OTH-{suffix.upper()}-{uuid.uuid4().hex[:6]}",
        academic_year="2026-2027",
        status="ACTIVE",
    )
    db.add_all([batch_a, other_class])
    await db.flush()

    other_batch = Batch(
        class_id=other_class.id,
        name=f"Batch Other-{suffix}",
        code=f"BAT-OTH-{suffix.upper()}-{uuid.uuid4().hex[:4]}",
        start_time=time(14, 0),
        end_time=time(16, 0),
        status="ACTIVE",
    )
    subject_obj = Subject(
        class_id=class_obj.id,
        name=f"Subject {suffix}",
        code=f"SUB-{suffix.upper()}-{uuid.uuid4().hex[:4]}",
        status="ACTIVE",
    )
    other_subject = Subject(
        class_id=other_class.id,
        name=f"Other Subject {suffix}",
        code=f"SUB-OTH-{suffix.upper()}-{uuid.uuid4().hex[:4]}",
        status="ACTIVE",
    )
    db.add_all([other_batch, subject_obj, other_subject])
    await db.flush()

    return class_obj, batch_a, subject_obj, other_class, other_batch, other_subject


async def create_student(
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


# ---------------------------------------------------------------------------
# Test Suite: Admin Student Attendance Workflow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_attendance_roster_empty_and_populated(async_client: AsyncClient, db_session: AsyncSession):
    """Test loading attendance roster: unmarked initially, then populated with existing attendance."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    u_stu1 = await create_user(db_session, UserRole.STUDENT, "Student One", f"s1_{u_suffix}@fundamics.test")
    u_stu2 = await create_user(db_session, UserRole.STUDENT, "Student Two", f"s2_{u_suffix}@fundamics.test")
    s1 = await create_student(db_session, u_stu1, class_obj.id, batch_a.id, f"1_{u_suffix}")
    s2 = await create_student(db_session, u_stu2, class_obj.id, batch_a.id, f"2_{u_suffix}")

    target_date = date(2026, 10, 5)

    # 1. Query roster on empty date
    res = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": target_date.isoformat(),
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["class_id"] == str(class_obj.id)
    assert data["batch_id"] == str(batch_a.id)
    assert data["subject_id"] == str(subject_obj.id)
    assert data["date"] == target_date.isoformat()
    assert data["is_holiday"] is False
    assert data["calendar_event_title"] is None
    assert data["total_students"] == 2
    assert data["marked_count"] == 0
    assert data["unmarked_count"] == 2
    assert len(data["students"]) == 2
    for item in data["students"]:
        assert item["status"] is None
        assert item["remarks"] is None
        assert item["attendance_id"] is None

    # 2. Add an existing attendance record for s1
    existing_att = StudentAttendance(
        student_id=s1.id,
        class_id=class_obj.id,
        batch_id=batch_a.id,
        date=target_date,
        status=AttendanceStatus.PRESENT,
        remarks="Arrived on time",
        source="MANUAL_ADMIN",
    )
    db_session.add(existing_att)
    await db_session.flush()

    # 3. Query roster again, now s1 is marked, s2 is unmarked
    res2 = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": target_date.isoformat(),
        },
        headers=make_auth_header(admin),
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["marked_count"] == 1
    assert data2["unmarked_count"] == 1

    s1_item = next(item for item in data2["students"] if item["student_id"] == str(s1.id))
    assert s1_item["status"] == "PRESENT"
    assert s1_item["remarks"] == "Arrived on time"
    assert s1_item["attendance_id"] == str(existing_att.id)

    s2_item = next(item for item in data2["students"] if item["student_id"] == str(s2.id))
    assert s2_item["status"] is None
    assert s2_item["attendance_id"] is None


@pytest.mark.asyncio
async def test_admin_attendance_roster_calendar_event_flagging(async_client: AsyncClient, db_session: AsyncSession):
    """Test that AcademicCalendarEvent holiday and non-holiday flags are correctly reflected in roster."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    holiday_date = date(2026, 10, 2)
    cal_event = AcademicCalendarEvent(
        title="Gandhi Jayanti",
        date=holiday_date,
        type=CalendarEventType.HOLIDAY,
        applies_to="ALL",
        created_by=admin.id,
    )
    db_session.add(cal_event)
    await db_session.flush()

    res = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": holiday_date.isoformat(),
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_holiday"] is True
    assert data["calendar_event_title"] == "Gandhi Jayanti"


@pytest.mark.asyncio
async def test_admin_attendance_roster_validation_errors(async_client: AsyncClient, db_session: AsyncSession):
    """Test validation errors on roster loading: missing class, mismatched batch/subject."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, other_class, other_batch, other_subject = await create_academic_setup(db_session, u_suffix)

    # 1. Non-existent class
    res = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(uuid.uuid4()),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-05",
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 404

    # 2. Batch belonging to other class
    res = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(other_batch.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-05",
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 422
    assert "Batch does not belong" in res.json()["error"]["message"]

    # 3. Subject belonging to other class
    res = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(other_subject.id),
            "date": "2026-10-05",
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 422
    assert "Subject does not belong" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_admin_attendance_submit_all_statuses_and_audit(async_client: AsyncClient, db_session: AsyncSession):
    """Test successful submission with PRESENT, ABSENT, LATE, EXCUSED and audit logging."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    # Create 4 students
    students = []
    for i in range(1, 5):
        u = await create_user(db_session, UserRole.STUDENT, f"Student {i}", f"s{i}_{u_suffix}@fundamics.test")
        st = await create_student(db_session, u, class_obj.id, batch_a.id, f"{i}_{u_suffix}")
        students.append(st)

    target_date = date(2026, 10, 6)
    payload = {
        "class_id": str(class_obj.id),
        "batch_id": str(batch_a.id),
        "subject_id": str(subject_obj.id),
        "date": target_date.isoformat(),
        "records": [
            {"student_id": str(students[0].id), "status": "PRESENT", "remarks": "On time"},
            {"student_id": str(students[1].id), "status": "ABSENT", "remarks": "Fever"},
            {"student_id": str(students[2].id), "status": "LATE", "remarks": "15 min delay"},
            {"student_id": str(students[3].id), "status": "EXCUSED", "remarks": "Family event"},
        ],
    }

    res = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json=payload,
        headers=make_auth_header(admin),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_submitted"] == 4
    assert data["created_count"] == 4
    assert data["updated_count"] == 0
    assert len(data["records"]) == 4

    # Verify database persistence
    att_res = await db_session.execute(
        select(StudentAttendance).where(StudentAttendance.date == target_date)
    )
    rows = att_res.scalars().all()
    assert len(rows) == 4
    for r in rows:
        assert r.source == "MANUAL_ADMIN"

    # Verify audit log entry
    audit_res = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "STUDENT_ATTENDANCE_RECORDED",
            AuditLog.actor_id == admin.id,
        )
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.resource_type == "student_attendance"
    assert audit.after_json["total_submitted"] == 4
    assert audit.after_json["created_count"] == 4


@pytest.mark.asyncio
async def test_admin_attendance_submit_upsert_update_existing_no_conflict(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test updating existing attendance records without uq_student_attendance_date conflict."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    u_stu1 = await create_user(db_session, UserRole.STUDENT, "Student 1", f"s1_{u_suffix}@fundamics.test")
    u_stu2 = await create_user(db_session, UserRole.STUDENT, "Student 2", f"s2_{u_suffix}@fundamics.test")
    s1 = await create_student(db_session, u_stu1, class_obj.id, batch_a.id, f"1_{u_suffix}")
    s2 = await create_student(db_session, u_stu2, class_obj.id, batch_a.id, f"2_{u_suffix}")

    target_date = date(2026, 10, 7)

    # First submission: s1 is ABSENT, s2 is PRESENT
    res1 = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": target_date.isoformat(),
            "records": [
                {"student_id": str(s1.id), "status": "ABSENT", "remarks": "Unexcused"},
                {"student_id": str(s2.id), "status": "PRESENT", "remarks": "Normal"},
            ],
        },
        headers=make_auth_header(admin),
    )
    assert res1.status_code == 200
    assert res1.json()["created_count"] == 2
    assert res1.json()["updated_count"] == 0

    # Second submission: student 1 arrived late -> update to LATE, student 2 marked EXCUSED
    res2 = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": target_date.isoformat(),
            "records": [
                {"student_id": str(s1.id), "status": "LATE", "remarks": "Arrived 20 mins late with note"},
                {"student_id": str(s2.id), "status": "EXCUSED", "remarks": "Left early for medical"},
            ],
        },
        headers=make_auth_header(admin),
    )
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    assert data2["created_count"] == 0
    assert data2["updated_count"] == 2

    # Verify roster confirms updated statuses
    roster_res = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": target_date.isoformat(),
        },
        headers=make_auth_header(admin),
    )
    assert roster_res.status_code == 200
    r_data = roster_res.json()
    s1_item = next(item for item in r_data["students"] if item["student_id"] == str(s1.id))
    s2_item = next(item for item in r_data["students"] if item["student_id"] == str(s2.id))
    assert s1_item["status"] == "LATE"
    assert s1_item["remarks"] == "Arrived 20 mins late with note"
    assert s2_item["status"] == "EXCUSED"
    assert s2_item["remarks"] == "Left early for medical"


@pytest.mark.asyncio
async def test_admin_attendance_submit_mixed_create_and_update(async_client: AsyncClient, db_session: AsyncSession):
    """Test submitting attendance with a mixture of existing and new student records."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    u_stu1 = await create_user(db_session, UserRole.STUDENT, "Student 1", f"s1_{u_suffix}@fundamics.test")
    u_stu2 = await create_user(db_session, UserRole.STUDENT, "Student 2", f"s2_{u_suffix}@fundamics.test")
    s1 = await create_student(db_session, u_stu1, class_obj.id, batch_a.id, f"1_{u_suffix}")
    s2 = await create_student(db_session, u_stu2, class_obj.id, batch_a.id, f"2_{u_suffix}")

    target_date = date(2026, 10, 8)

    # Pre-record s1
    att1 = StudentAttendance(
        student_id=s1.id,
        class_id=class_obj.id,
        batch_id=batch_a.id,
        date=target_date,
        status=AttendanceStatus.ABSENT,
        remarks=None,
        source="MANUAL_ADMIN",
    )
    db_session.add(att1)
    await db_session.flush()

    # Submit for both s1 (update) and s2 (create)
    res = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": target_date.isoformat(),
            "records": [
                {"student_id": str(s1.id), "status": "PRESENT", "remarks": "Corrected"},
                {"student_id": str(s2.id), "status": "PRESENT", "remarks": "New entry"},
            ],
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["created_count"] == 1
    assert data["updated_count"] == 1


@pytest.mark.asyncio
async def test_admin_attendance_submit_duplicate_student_in_payload_rejected(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that submitting duplicate student IDs in a single request is rejected with 422."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    u_stu1 = await create_user(db_session, UserRole.STUDENT, "Student 1", f"s1_{u_suffix}@fundamics.test")
    s1 = await create_student(db_session, u_stu1, class_obj.id, batch_a.id, f"1_{u_suffix}")

    res = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-09",
            "records": [
                {"student_id": str(s1.id), "status": "PRESENT"},
                {"student_id": str(s1.id), "status": "ABSENT"},
            ],
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 422
    assert "Duplicate student" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_admin_attendance_submit_unenrolled_student_rejected(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test that submitting a student who is not enrolled in this class/batch is rejected."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, other_class, other_batch, _ = await create_academic_setup(db_session, u_suffix)

    # Student enrolled in other_batch
    u_other = await create_user(db_session, UserRole.STUDENT, "Other Student", f"other_{u_suffix}@fundamics.test")
    s_other = await create_student(db_session, u_other, other_class.id, other_batch.id, f"oth_{u_suffix}")

    res = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-09",
            "records": [
                {"student_id": str(s_other.id), "status": "PRESENT"},
            ],
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 422
    assert "not an active enrolled student" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_admin_attendance_submit_academic_calendar_holiday_rule_and_override(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Test academic-calendar holiday blocking and allow_holiday_override behavior."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    u_stu1 = await create_user(db_session, UserRole.STUDENT, "Student 1", f"s1_{u_suffix}@fundamics.test")
    s1 = await create_student(db_session, u_stu1, class_obj.id, batch_a.id, f"1_{u_suffix}")

    holiday_date = date(2026, 11, 14)
    cal_event = AcademicCalendarEvent(
        title="Diwali Break",
        date=holiday_date,
        type=CalendarEventType.HOLIDAY,
        applies_to="ALL",
        created_by=admin.id,
    )
    db_session.add(cal_event)
    await db_session.flush()

    # 1. Submission blocked without override
    res1 = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": holiday_date.isoformat(),
            "allow_holiday_override": False,
            "records": [{"student_id": str(s1.id), "status": "PRESENT"}],
        },
        headers=make_auth_header(admin),
    )
    assert res1.status_code == 422
    assert "marked as HOLIDAY ('Diwali Break')" in res1.json()["error"]["message"]

    # 2. Submission allowed with allow_holiday_override=True
    res2 = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": holiday_date.isoformat(),
            "allow_holiday_override": True,
            "records": [{"student_id": str(s1.id), "status": "PRESENT", "remarks": "Special remedial class"}],
        },
        headers=make_auth_header(admin),
    )
    assert res2.status_code == 200
    assert res2.json()["created_count"] == 1


@pytest.mark.asyncio
async def test_admin_attendance_rbac_enforcement(async_client: AsyncClient, db_session: AsyncSession):
    """Enforce that student and teacher tokens receive 403 Forbidden on admin attendance APIs."""
    u_suffix = uuid.uuid4().hex[:8]
    class_obj, batch_a, subject_obj, _, _, _ = await create_academic_setup(db_session, u_suffix)

    u_stu = await create_user(db_session, UserRole.STUDENT, "Student User", f"stu_{u_suffix}@fundamics.test")
    u_teacher = await create_user(db_session, UserRole.TEACHER, "Teacher User", f"tea_{u_suffix}@fundamics.test")

    # 1. Student access -> 403 Forbidden
    roster_stu = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-10",
        },
        headers=make_auth_header(u_stu),
    )
    assert roster_stu.status_code == 403

    submit_stu = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-10",
            "records": [{"student_id": str(uuid.uuid4()), "status": "PRESENT"}],
        },
        headers=make_auth_header(u_stu),
    )
    assert submit_stu.status_code == 403

    # 2. Teacher access -> 403 Forbidden
    roster_tea = await async_client.get(
        "/api/v1/admin/attendance/roster",
        params={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-10",
        },
        headers=make_auth_header(u_teacher),
    )
    assert roster_tea.status_code == 403

    submit_tea = await async_client.post(
        "/api/v1/admin/attendance/submit",
        json={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "subject_id": str(subject_obj.id),
            "date": "2026-10-10",
            "records": [{"student_id": str(uuid.uuid4()), "status": "PRESENT"}],
        },
        headers=make_auth_header(u_teacher),
    )
    assert submit_tea.status_code == 403


@pytest.mark.asyncio
async def test_excel_preview_endpoint_remains_intact(async_client: AsyncClient, db_session: AsyncSession):
    """Ensure existing Excel preview endpoint is unchanged and operational."""
    u_suffix = uuid.uuid4().hex[:8]
    admin = await create_user(db_session, UserRole.ADMIN, "Admin User", f"admin_{u_suffix}@fundamics.test")
    class_obj, batch_a, _, _, _, _ = await create_academic_setup(db_session, u_suffix)

    # Calling preview without file or records triggers expected 422
    res = await async_client.post(
        "/api/v1/admin/attendance/preview",
        data={
            "class_id": str(class_obj.id),
            "batch_id": str(batch_a.id),
            "attendance_date": "2026-10-10",
        },
        headers=make_auth_header(admin),
    )
    assert res.status_code == 422
    assert "Either an Excel file (.xlsx) or attendance records must be provided" in res.json()["error"]["message"]
