import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit import record_audit_log
from src.core.permissions import require_admin
from src.database import get_db
from src.models.system import AcademicCalendarEvent, InstituteSettings, AuditLog
from src.models.user import User
from src.schemas.system import (
    CalendarEventCreateRequest,
    CalendarEventResponse,
    InstituteSettingsUpdateRequest,
    InstituteSettingsResponse,
    AuditLogResponse,
)

admin_system_router = APIRouter(prefix="/admin", tags=["Admin — System, Settings & Audit"])


# Calendar Events
@admin_system_router.post("/calendar/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    req: CalendarEventCreateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Create academic calendar event (Holiday, Exam, Closed, Special Class)."""
    event = AcademicCalendarEvent(
        title=req.title.strip(),
        date=req.date,
        type=req.type,
        applies_to=req.applies_to,
        class_id=req.class_id,
        batch_id=req.batch_id,
        created_by=current_admin.id,
    )
    db.add(event)
    await db.flush()

    request_id = getattr(request.state, "request_id", None)
    await record_audit_log(
        db=db,
        action="CALENDAR_EVENT_CREATED",
        resource_type="calendar_event",
        resource_id=str(event.id),
        actor_id=current_admin.id,
        after_json={"title": event.title, "date": str(event.date), "type": event.type.value},
        request_id=request_id,
    )
    await db.commit()
    return CalendarEventResponse.model_validate(event)


@admin_system_router.get("/calendar/events", response_model=List[CalendarEventResponse], status_code=status.HTTP_200_OK)
async def list_calendar_events(
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query academic calendar events."""
    res = await db.execute(select(AcademicCalendarEvent).order_by(AcademicCalendarEvent.date.asc()))
    return [CalendarEventResponse.model_validate(e) for e in res.scalars().all()]


# Institute Settings
@admin_system_router.get("/settings/institute", response_model=InstituteSettingsResponse, status_code=status.HTTP_200_OK)
async def get_institute_settings(
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Query institute settings."""
    res = await db.execute(select(InstituteSettings))
    settings_obj = res.scalar_one_or_none()
    if not settings_obj:
        # Create singleton default
        settings_obj = InstituteSettings(
            status="ACTIVE",
            attendance_required_hours=8,
            timezone="Asia/Kolkata",
            attendance_cutoff_time="23:59",
            missing_checkout_policy="INCOMPLETE",
            notifications_enabled=True,
        )
        db.add(settings_obj)
        await db.commit()
    return InstituteSettingsResponse.model_validate(settings_obj)


@admin_system_router.patch("/settings/institute", response_model=InstituteSettingsResponse, status_code=status.HTTP_200_OK)
async def update_institute_settings(
    req: InstituteSettingsUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Update institute configuration settings."""
    res = await db.execute(select(InstituteSettings))
    settings_obj = res.scalar_one_or_none()
    if not settings_obj:
        settings_obj = InstituteSettings()
        db.add(settings_obj)

    update_data = req.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(settings_obj, field, val)

    settings_obj.updated_by = current_admin.id

    request_id = getattr(request.state, "request_id", None)
    await record_audit_log(
        db=db,
        action="SETTINGS_UPDATED",
        resource_type="institute_settings",
        resource_id=str(settings_obj.id),
        actor_id=current_admin.id,
        after_json=update_data,
        request_id=request_id,
    )
    await db.commit()
    return InstituteSettingsResponse.model_validate(settings_obj)


# Audit Logs
@admin_system_router.get("/audit-logs", response_model=List[AuditLogResponse], status_code=status.HTTP_200_OK)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Review immutable system audit logs."""
    res = await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    )
    return [AuditLogResponse.model_validate(a) for a in res.scalars().all()]
