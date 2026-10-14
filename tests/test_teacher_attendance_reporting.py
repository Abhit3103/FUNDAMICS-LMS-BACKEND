import uuid
import pytest
from datetime import date, datetime, timezone
from httpx import AsyncClient
from src.core.security import hash_password, create_access_token
from src.models.user import User, Teacher, UserRole, UserStatus
from src.models.teacher_attendance import TeacherAttendance, TeacherAttendanceStatus


@pytest.mark.asyncio
async def test_teacher_attendance_listing_and_reporting(async_client: AsyncClient, db_session):
    admin = User(
        name="Admin Attendance",
        email="admin_att@fundamics.com",
        password_hash=hash_password("Admin@123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db_session.add(admin)

    t_user = User(
        name="Prof. Sharma",
        email="prof_sharma@fundamics.com",
        password_hash=hash_password("Teacher@123"),
        role=UserRole.TEACHER,
        status=UserStatus.ACTIVE,
    )
    db_session.add(t_user)
    await db_session.flush()

    teacher = Teacher(
        user_id=t_user.id,
        teacher_code="TCH-SHARMA",
        biometric_employee_id="BIO-001",
        status="ACTIVE",
    )
    db_session.add(teacher)
    await db_session.flush()

    admin_token = create_access_token(subject=str(admin.id), role=UserRole.ADMIN.value)
    teacher_token = create_access_token(subject=str(t_user.id), role=UserRole.TEACHER.value)

    # Seed teacher attendance records
    rec1 = TeacherAttendance(
        teacher_id=teacher.id,
        date=date(2026, 10, 1),
        check_in_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
        check_out_at=datetime(2026, 10, 1, 17, 30, tzinfo=timezone.utc),
        served_minutes=510,
        required_minutes=480,
        status=TeacherAttendanceStatus.PRESENT,
    )
    rec2 = TeacherAttendance(
        teacher_id=teacher.id,
        date=date(2026, 10, 2),
        check_in_at=datetime(2026, 10, 2, 9, 15, tzinfo=timezone.utc),
        check_out_at=datetime(2026, 10, 2, 13, 15, tzinfo=timezone.utc),
        served_minutes=240,
        required_minutes=480,
        status=TeacherAttendanceStatus.HALF_DAY,
    )
    db_session.add_all([rec1, rec2])
    await db_session.flush()

    # 1. Admin query teacher attendance list
    list_res = await async_client.get(
        f"/api/v1/admin/teacher-attendance?teacher_id={teacher.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_res.status_code == 200
    records = list_res.json()
    assert len(records) >= 2
    assert records[0]["teacher_code"] == "TCH-SHARMA"

    # Filter by status
    present_res = await async_client.get(
        f"/api/v1/admin/teacher-attendance?status=PRESENT",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert present_res.status_code == 200
    assert all(r["status"] == "PRESENT" for r in present_res.json())

    # 2. Admin aggregate report
    report_res = await async_client.get(
        "/api/v1/admin/teacher-attendance/report?start_date=2026-10-01&end_date=2026-10-05",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert report_res.status_code == 200
    rep_data = report_res.json()
    assert rep_data["total_records"] >= 2
    assert rep_data["present_count"] >= 1
    assert rep_data["half_day_count"] >= 1
    assert rep_data["total_hours_served"] > 0

    # 3. Teacher query own records
    teacher_records_res = await async_client.get(
        "/api/v1/teacher/me/attendance/records",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert teacher_records_res.status_code == 200
    t_recs = teacher_records_res.json()
    assert len(t_recs) >= 2
    assert t_recs[0]["teacher_id"] == str(teacher.id)
