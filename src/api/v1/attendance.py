import uuid
from datetime import date
from typing import List
from fastapi import APIRouter, Depends, Request, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin, require_student
from src.database import get_db
from src.models.user import User
from src.schemas.student_attendance import (
    AttendanceRecordInput,
    AttendanceImportPreviewResponse,
    ConfirmAttendanceImportResponse,
    StudentAttendanceSummary,
)
from src.services.student_attendance_service import student_attendance_service

# Admin Attendance Router
admin_attendance_router = APIRouter(prefix="/admin", tags=["Admin — Student Attendance"])

# Student Attendance Router
student_attendance_router = APIRouter(prefix="/student", tags=["Student — My Attendance"])


@admin_attendance_router.post("/attendance/preview", response_model=AttendanceImportPreviewResponse, status_code=status.HTTP_200_OK)
async def preview_attendance_import(
    class_id: uuid.UUID = Form(...),
    batch_id: uuid.UUID = Form(...),
    attendance_date: date = Form(...),
    records: List[AttendanceRecordInput] = Form(...),
    request: Request = None,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Validate staged student attendance before committing to database."""
    request_id = getattr(request.state, "request_id", None) if request else None
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
