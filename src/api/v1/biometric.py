import uuid
from datetime import date
from typing import List
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin, require_teacher
from src.database import get_db
from src.models.user import User
from src.schemas.teacher_attendance import (
    BiometricEventWebhookPayload,
    IngestBiometricEventsResponse,
    TeacherAttendanceDaySummary,
    TeacherAttendanceOverallSummary,
)
from src.services.biometric_service import biometric_service

integrations_router = APIRouter(prefix="/integrations", tags=["Integrations — Biometric Devices"])
teacher_attendance_router = APIRouter(prefix="/teacher", tags=["Teacher — My Attendance"])
admin_teacher_attendance_router = APIRouter(prefix="/admin", tags=["Admin — Teacher Attendance"])


# Secureye Device Ingestion Webhook
@integrations_router.post(
    "/biometric/secureye/events",
    response_model=IngestBiometricEventsResponse,
    status_code=status.HTTP_200_OK,
)
async def ingest_biometric_events(
    events: List[BiometricEventWebhookPayload],
    request: Request,
    x_device_secret: str = Header(..., description="Secret token shared with biometric device"),
    db: AsyncSession = Depends(get_db),
):
    """Secureye device webhook: Ingest, deduplicate, and map employee identifiers."""
    request_id = getattr(request.state, "request_id", None)
    return await biometric_service.ingest_device_events(
        db=db,
        device_secret=x_device_secret,
        events=events,
        request_id=request_id,
    )


# Teacher Read-Only My Attendance Endpoints
@teacher_attendance_router.get(
    "/me/attendance/summary",
    response_model=TeacherAttendanceOverallSummary,
    status_code=status.HTTP_200_OK,
)
async def get_my_attendance_summary(
    current_user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    """Teacher-only: Query authenticated teacher's attendance summary and total served hours."""
    return await biometric_service.get_teacher_summary(
        db=db,
        teacher_id=current_user.teacher.id,
    )


# Admin Calculate Daily Attendance Endpoint
@admin_teacher_attendance_router.post(
    "/teacher-attendance/{teacher_id}/calculate",
    response_model=TeacherAttendanceDaySummary,
    status_code=status.HTTP_200_OK,
)
async def calculate_teacher_attendance(
    teacher_id: uuid.UUID,
    target_date: date,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Trigger daily calculation for a teacher on a specific date."""
    return await biometric_service.calculate_teacher_daily(
        db=db,
        teacher_id=teacher_id,
        target_date=target_date,
    )
