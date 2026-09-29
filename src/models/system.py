import enum
import uuid
from datetime import date, datetime
from typing import Optional
from sqlalchemy import String, Integer, Date, DateTime, Boolean, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import TimeStampedUUIDModel


class CalendarEventType(str, enum.Enum):
    HOLIDAY = "HOLIDAY"
    CLOSED = "CLOSED"
    EXAM = "EXAM"
    SPECIAL_CLASS = "SPECIAL_CLASS"


class AcademicCalendarEvent(TimeStampedUUIDModel):
    __tablename__ = "academic_calendar_events"

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    type: Mapped[CalendarEventType] = mapped_column(
        Enum(CalendarEventType, name="calendar_event_type_enum", native_enum=False),
        nullable=False,
    )
    applies_to: Mapped[str] = mapped_column(String(50), default="ALL", nullable=False)
    class_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class NotificationRecord(TimeStampedUUIDModel):
    __tablename__ = "notification_records"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    recipient_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    payload_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class AuditLog(TimeStampedUUIDModel):
    __tablename__ = "audit_logs"

    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    before_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)


class InstituteSettings(TimeStampedUUIDModel):
    __tablename__ = "institute_settings"

    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    attendance_required_hours: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)
    attendance_cutoff_time: Mapped[str] = mapped_column(String(10), default="23:59", nullable=False)
    missing_checkout_policy: Mapped[str] = mapped_column(String(30), default="INCOMPLETE", nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
