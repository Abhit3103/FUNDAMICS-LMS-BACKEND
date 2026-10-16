import uuid
from datetime import date
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, Header, Request, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.permissions import require_admin, require_teacher
from src.database import get_db
from src.models.user import User
from src.models.teacher_attendance import TeacherAttendanceStatus
from src.schemas.teacher_attendance import (
    BiometricEventWebhookPayload,
    IngestBiometricEventsResponse,
    TeacherAttendanceDaySummary,
    TeacherAttendanceOverallSummary,
    TeacherAttendanceRecordResponse,
    TeacherAttendanceReportResponse,
    BiometricDeviceRegisterRequest,
    BiometricDeviceUpdateRequest,
    BiometricDeviceResponse,
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
    events: Union[List[BiometricEventWebhookPayload], BiometricEventWebhookPayload] = Body(
        ...,
        description="Single biometric event or batch of biometric events",
    ),
    request: Request = None,
    x_device_secret: str = Header(..., description="Secret token shared with biometric device"),
    db: AsyncSession = Depends(get_db),
):
    """Secureye device webhook: Ingest, deduplicate, and map employee identifiers."""
    request_id = getattr(request.state, "request_id", None) if request and hasattr(request, "state") else None
    event_list = [events] if isinstance(events, BiometricEventWebhookPayload) else events
    return await biometric_service.ingest_device_events(
        db=db,
        device_secret=x_device_secret,
        events=event_list,
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


@teacher_attendance_router.get(
    "/me/attendance/records",
    response_model=List[TeacherAttendanceRecordResponse],
    status_code=status.HTTP_200_OK,
)
async def get_my_attendance_records(
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    """Teacher-only: Query authenticated teacher's historical attendance records."""
    return await biometric_service.get_teacher_own_records(
        db=db,
        teacher_id=current_user.teacher.id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


# Admin Teacher Attendance Endpoints
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


@admin_teacher_attendance_router.get(
    "/teacher-attendance",
    response_model=List[TeacherAttendanceRecordResponse],
    status_code=status.HTTP_200_OK,
)
async def list_teacher_attendance(
    teacher_id: Optional[uuid.UUID] = Query(None, description="Filter by teacher ID"),
    date: Optional[date] = Query(None, description="Filter by exact date"),
    start_date: Optional[date] = Query(None, description="Filter start date"),
    end_date: Optional[date] = Query(None, description="Filter end date"),
    status_filter: Optional[TeacherAttendanceStatus] = Query(None, alias="status", description="Filter by attendance status"),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query teacher attendance records with comprehensive filters."""
    return await biometric_service.list_teacher_attendance(
        db=db,
        teacher_id=teacher_id,
        target_date=date,
        start_date=start_date,
        end_date=end_date,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@admin_teacher_attendance_router.get(
    "/teacher-attendance/report",
    response_model=TeacherAttendanceReportResponse,
    status_code=status.HTTP_200_OK,
)
async def get_teacher_attendance_report(
    start_date: date = Query(..., description="Report start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Report end date (YYYY-MM-DD)"),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Aggregate staff attendance summary report across date range."""
    return await biometric_service.get_teacher_attendance_report(
        db=db,
        start_date=start_date,
        end_date=end_date,
    )


# Admin Biometric Hardware Registry Endpoints
@admin_teacher_attendance_router.post(
    "/biometric-devices",
    response_model=BiometricDeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_biometric_device(
    payload: BiometricDeviceRegisterRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Register a new biometric device with unique external_device_id and secret."""
    request_id = getattr(request.state, "request_id", None) if request and hasattr(request, "state") else None
    return await biometric_service.register_device(
        db=db,
        req=payload,
        request_id=request_id,
    )


@admin_teacher_attendance_router.get(
    "/biometric-devices",
    response_model=List[BiometricDeviceResponse],
    status_code=status.HTTP_200_OK,
)
async def list_biometric_devices(
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: List all registered biometric hardware devices."""
    return await biometric_service.list_devices(db=db)


@admin_teacher_attendance_router.patch(
    "/biometric-devices/{device_id}",
    response_model=BiometricDeviceResponse,
    status_code=status.HTTP_200_OK,
)
async def update_biometric_device(
    device_id: uuid.UUID,
    payload: BiometricDeviceUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update device status (ACTIVE/INACTIVE), name, model, or rotate secret."""
    request_id = getattr(request.state, "request_id", None) if request and hasattr(request, "state") else None
    return await biometric_service.update_device(
        db=db,
        device_id=device_id,
        req=payload,
        request_id=request_id,
    )
