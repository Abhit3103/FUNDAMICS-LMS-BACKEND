import uuid
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ValidationError
from src.core.permissions import require_admin, require_student
from src.database import get_db
from src.models.user import User
from src.schemas.student_attendance import (
    AttendanceRecordInput,
    AttendanceImportPreviewResponse,
    ConfirmAttendanceImportResponse,
    StudentAttendanceSummary,
    StudentAttendanceRosterResponse,
    StudentAttendanceSubmitRequest,
    StudentAttendanceSubmitResponse,
    StudentMonthlyAttendanceResponse,
)
from src.services.student_attendance_service import student_attendance_service

# Admin Attendance Router
admin_attendance_router = APIRouter(prefix="/admin", tags=["Admin — Student Attendance"])

# Student Attendance Router
student_attendance_router = APIRouter(prefix="/student", tags=["Student — My Attendance"])


@admin_attendance_router.get(
    "/attendance/roster",
    response_model=StudentAttendanceRosterResponse,
    status_code=status.HTTP_200_OK,
)
async def get_attendance_roster(
    class_id: uuid.UUID = Query(..., description="Target class ID"),
    batch_id: uuid.UUID = Query(..., description="Target batch ID"),
    subject_id: uuid.UUID = Query(..., description="Target subject ID"),
    date: Optional[date] = Query(None, description="Attendance date (YYYY-MM-DD)"),
    attendance_date: Optional[date] = Query(None, description="Attendance date (YYYY-MM-DD)"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Load students by Class + Batch + Subject + Date, including existing attendance records."""
    target_date = date or attendance_date
    if not target_date:
        raise ValidationError("Query parameter 'date' or 'attendance_date' is required")
    return await student_attendance_service.get_attendance_roster(
        db=db,
        class_id=class_id,
        batch_id=batch_id,
        subject_id=subject_id,
        attendance_date=target_date,
    )


@admin_attendance_router.get(
    "/attendance",
    response_model=StudentAttendanceRosterResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_attendance_roster_alias(
    class_id: uuid.UUID = Query(..., description="Target class ID"),
    batch_id: uuid.UUID = Query(..., description="Target batch ID"),
    subject_id: uuid.UUID = Query(..., description="Target subject ID"),
    date: Optional[date] = Query(None, description="Attendance date (YYYY-MM-DD)"),
    attendance_date: Optional[date] = Query(None, description="Attendance date (YYYY-MM-DD)"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_attendance_roster(
        class_id=class_id,
        batch_id=batch_id,
        subject_id=subject_id,
        date=date,
        attendance_date=attendance_date,
        current_admin=current_admin,
        db=db,
    )


@admin_attendance_router.post(
    "/attendance/submit",
    response_model=StudentAttendanceSubmitResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_attendance_roster(
    req: StudentAttendanceSubmitRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Submit or update student attendance list with PRESENT, ABSENT, LATE, EXCUSED and optional remarks."""
    request_id = getattr(request.state, "request_id", None)
    target_date = req.date or req.attendance_date
    if not target_date:
        raise ValidationError("Field 'date' or 'attendance_date' is required in request body")
    return await student_attendance_service.submit_attendance_roster(
        db=db,
        class_id=req.class_id,
        batch_id=req.batch_id,
        subject_id=req.subject_id,
        attendance_date=target_date,
        records=req.records,
        actor_id=current_admin.id,
        allow_holiday_override=req.allow_holiday_override,
        request_id=request_id,
    )


@admin_attendance_router.post(
    "/attendance",
    response_model=StudentAttendanceSubmitResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def submit_attendance_roster_alias(
    req: StudentAttendanceSubmitRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await submit_attendance_roster(
        req=req,
        request=request,
        current_admin=current_admin,
        db=db,
    )



@admin_attendance_router.post("/attendance/preview", response_model=AttendanceImportPreviewResponse, status_code=status.HTTP_200_OK)
async def preview_attendance_import(
    class_id: uuid.UUID = Form(...),
    batch_id: uuid.UUID = Form(...),
    attendance_date: date = Form(...),
    file: Optional[UploadFile] = File(None),
    records: Optional[List[AttendanceRecordInput]] = Form(None),
    request: Request = None,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Validate staged student attendance before committing to database."""
    request_id = getattr(request.state, "request_id", None) if request else None

    if file and file.filename:
        content = await file.read()
        parsed_records = student_attendance_service.parse_excel_workbook(
            file_bytes=content,
            filename=file.filename,
        )
        return await student_attendance_service.parse_and_validate_records(
            db=db,
            class_id=class_id,
            batch_id=batch_id,
            attendance_date=attendance_date,
            records=parsed_records,
            uploaded_by=current_admin.id,
            filename=file.filename,
            request_id=request_id,
        )
    elif records is not None and len(records) > 0:
        return await student_attendance_service.parse_and_validate_records(
            db=db,
            class_id=class_id,
            batch_id=batch_id,
            attendance_date=attendance_date,
            records=[r.model_dump() for r in records],
            uploaded_by=current_admin.id,
            filename="manual_staged_import.json",
            request_id=request_id,
        )
    else:
        raise ValidationError("Either an Excel file (.xlsx) or attendance records must be provided")


@admin_attendance_router.post("/attendance/confirm/{import_id}", response_model=ConfirmAttendanceImportResponse, status_code=status.HTTP_200_OK)
async def confirm_attendance_import(
    import_id: uuid.UUID,
    records: List[AttendanceRecordInput],
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Atomically commit validated attendance entries and write audit log."""
    request_id = getattr(request.state, "request_id", None)
    return await student_attendance_service.commit_import(
        db=db,
        import_id=import_id,
        validated_rows=[r.model_dump() for r in records],
        actor_id=current_admin.id,
        request_id=request_id,
    )


@student_attendance_router.get("/me/attendance/summary", response_model=StudentAttendanceSummary, status_code=status.HTTP_200_OK)
async def get_my_attendance_summary(
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Student-only: Query authenticated student's attendance summary and analytics."""
    return await student_attendance_service.get_student_summary(
        db=db,
        student_id=current_user.student.id,
    )


@student_attendance_router.get(
    "/me/attendance/logs",
    response_model=StudentMonthlyAttendanceResponse,
    status_code=status.HTTP_200_OK,
)
async def get_my_attendance_logs(
    month: str = Query(
        ...,
        description="Target month in YYYY-MM format",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Student-only: Query authenticated student's day-wise attendance log records for a calendar month."""
    return await student_attendance_service.get_student_monthly_logs(
        db=db,
        student_id=current_user.student.id,
        month=month,
    )
