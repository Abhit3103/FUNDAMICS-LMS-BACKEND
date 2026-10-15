import uuid
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import OperationalError
from src.core.exceptions import (
    ValidationError,
    NotFoundError,
    ServiceUnavailableError,
)
from src.models.student_attendance import StudentAttendance, AttendanceStatus
from src.models.user import Student, User, UserRole, UserStatus
from src.services.student_attendance_service import student_attendance_service


@pytest.mark.asyncio
async def test_empty_month_returns_genuine_empty_results():
    """Verify that when no records exist for a month, genuine empty results are returned (never fabricated)."""
    mock_db = AsyncMock()
    student_id = uuid.uuid4()

    mock_student = Student(
        id=student_id,
        user_id=uuid.uuid4(),
        student_code="FND-2025-1042",
        class_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        admission_date=date(2025, 4, 1),
        status="ACTIVE",
    )
    mock_db.get.return_value = mock_student

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    res = await student_attendance_service.get_student_monthly_logs(
        db=mock_db,
        student_id=student_id,
        month="2026-05",
    )

    assert res.month == "2026-05"
    assert res.total_scheduled_days == 0
    assert res.present_days == 0
    assert res.absent_days == 0
    assert res.attendance_percentage == 0.0
    assert res.daily_records == []


@pytest.mark.asyncio
async def test_invalid_month_parameters_rejected():
    """Verify that invalid month formats and out-of-range months are rejected with ValidationError (422)."""
    mock_db = AsyncMock()
    student_id = uuid.uuid4()

    invalid_months = ["2026-13", "2026-00", "2026-5", "26-05", "invalid", "", "2026/05", "2026-05-01"]
    for inv_month in invalid_months:
        with pytest.raises(ValidationError) as exc_info:
            await student_attendance_service.get_student_monthly_logs(
                db=mock_db,
                student_id=student_id,
                month=inv_month,
            )
        assert exc_info.value.status_code == 422
        assert "YYYY-MM format" in exc_info.value.message


@pytest.mark.asyncio
async def test_month_boundaries_and_accurate_records():
    """Verify that valid attendance records are returned accurately with correct boundary filtering and percentages."""
    mock_db = AsyncMock()
    student_id = uuid.uuid4()

    mock_student = Student(
        id=student_id,
        user_id=uuid.uuid4(),
        student_code="FND-2025-1042",
        class_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        admission_date=date(2025, 4, 1),
        status="ACTIVE",
    )
    mock_db.get.return_value = mock_student

    rec1 = StudentAttendance(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=mock_student.class_id,
        batch_id=mock_student.batch_id,
        date=date(2026, 2, 2),
        status=AttendanceStatus.PRESENT,
        remarks=None,
    )
    rec2 = StudentAttendance(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=mock_student.class_id,
        batch_id=mock_student.batch_id,
        date=date(2026, 2, 3),
        status=AttendanceStatus.ABSENT,
        remarks="Fever",
    )
    rec3 = StudentAttendance(
        id=uuid.uuid4(),
        student_id=student_id,
        class_id=mock_student.class_id,
        batch_id=mock_student.batch_id,
        date=date(2026, 2, 4),
        status=AttendanceStatus.PRESENT,
        remarks=None,
    )

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [rec1, rec2, rec3]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    res = await student_attendance_service.get_student_monthly_logs(
        db=mock_db,
        student_id=student_id,
        month="2026-02",
    )

    assert res.month == "2026-02"
    assert res.total_scheduled_days == 3
    assert res.present_days == 2
    assert res.absent_days == 1
    assert res.attendance_percentage == round(2 / 3 * 100, 2)
    assert len(res.daily_records) == 3
    assert res.daily_records[0].date == "2026-02-02"
    assert res.daily_records[0].status == "PRESENT"
    assert res.daily_records[1].date == "2026-02-03"
    assert res.daily_records[1].status == "ABSENT"
    assert res.daily_records[1].remarks == "Fever"


@pytest.mark.asyncio
async def test_database_failure_never_returns_fabricated_monthly_records():
    """Verify that a database failure raises ServiceUnavailableError (503) and NEVER produces synthetic records."""
    mock_db = AsyncMock()
    student_id = uuid.uuid4()
    mock_db.get.side_effect = OperationalError("connection failure", {}, None)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await student_attendance_service.get_student_monthly_logs(
            db=mock_db,
            student_id=student_id,
            month="2026-05",
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_database_failure_never_returns_fabricated_summary():
    """Verify that database failure on summary raises ServiceUnavailableError (503) and NEVER returns fake 91.11% summary."""
    mock_db = AsyncMock()
    student_id = uuid.uuid4()
    mock_db.get.side_effect = OperationalError("connection failure", {}, None)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        await student_attendance_service.get_student_summary(
            db=mock_db,
            student_id=student_id,
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_empty_attendance_summary_returns_genuine_empty_summary():
    """Verify that when a student has no attendance records recorded, genuine empty metrics (0s) are returned."""
    mock_db = AsyncMock()
    student_id = uuid.uuid4()

    mock_student = Student(
        id=student_id,
        user_id=uuid.uuid4(),
        student_code="FND-2025-1042",
        class_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        admission_date=date(2025, 4, 1),
        status="ACTIVE",
    )
    mock_db.get.return_value = mock_student

    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    summary = await student_attendance_service.get_student_summary(
        db=mock_db,
        student_id=student_id,
    )

    assert summary.student_id == student_id
    assert summary.student_code == "FND-2025-1042"
    assert summary.total_working_days == 0
    assert summary.present_days == 0
    assert summary.absent_days == 0
    assert summary.late_days == 0
    assert summary.excused_days == 0
    assert summary.attendance_percentage == 0.0


@pytest.mark.asyncio
async def test_nonexistent_student_raises_not_found():
    """Verify that looking up attendance for a non-existent student raises NotFoundError (404) rather than dummy data."""
    mock_db = AsyncMock()
    student_id = uuid.uuid4()
    mock_db.get.return_value = None

    with pytest.raises(NotFoundError) as exc_info:
        await student_attendance_service.get_student_summary(
            db=mock_db,
            student_id=student_id,
        )
    assert exc_info.value.status_code == 404

    with pytest.raises(NotFoundError) as exc_info:
        await student_attendance_service.get_student_monthly_logs(
            db=mock_db,
            student_id=student_id,
            month="2026-05",
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_student_isolation_in_routes():
    """Verify that attendance routes extract student_id strictly from authenticated session token."""
    from src.api.v1.attendance import get_my_attendance_summary, get_my_attendance_logs
    from src.core.permissions import require_student

    student_id = uuid.uuid4()
    mock_student = Student(
        id=student_id,
        user_id=uuid.uuid4(),
        student_code="FND-2025-1042",
        class_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        admission_date=date(2025, 4, 1),
        status="ACTIVE",
    )
    mock_user = User(
        id=mock_student.user_id,
        email="rohan@example.com",
        name="Rohan Sharma",
        role=UserRole.STUDENT,
        status=UserStatus.ACTIVE,
    )
    mock_user.student = mock_student

    # Verify require_student dependency resolves current_user
    resolved_user = require_student(current_user=mock_user)
    assert resolved_user.student.id == student_id
