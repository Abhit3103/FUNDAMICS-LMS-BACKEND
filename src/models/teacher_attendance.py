import enum
import uuid
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Date, DateTime, Enum, ForeignKey, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import TimeStampedUUIDModel


class BiometricEventType(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class TeacherAttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HALF_DAY = "HALF_DAY"
    INCOMPLETE = "INCOMPLETE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    HOLIDAY = "HOLIDAY"


class BiometricDevice(TimeStampedUUIDModel):
    __tablename__ = "biometric_devices"

    external_device_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    secret_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    events: Mapped[List["BiometricEvent"]] = relationship("BiometricEvent", back_populates="device")


class BiometricEvent(TimeStampedUUIDModel):
    __tablename__ = "biometric_events"
    __table_args__ = (
        UniqueConstraint("device_id", "external_event_id", name="uq_device_external_event"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("biometric_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_event_id: Mapped[str] = mapped_column(String(150), nullable=False)
    employee_identifier: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    teacher_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teachers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[BiometricEventType] = mapped_column(
        Enum(BiometricEventType, name="biometric_event_type_enum", native_enum=False),
        nullable=False,
    )
    event_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    raw_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    device: Mapped["BiometricDevice"] = relationship("BiometricDevice", back_populates="events")
    teacher: Mapped[Optional["Teacher"]] = relationship("Teacher", back_populates="biometric_events")


class TeacherAttendance(TimeStampedUUIDModel):
    __tablename__ = "teacher_attendance"
    __table_args__ = (
        UniqueConstraint("teacher_id", "date", name="uq_teacher_attendance_date"),
    )

    teacher_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    served_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[TeacherAttendanceStatus] = mapped_column(
        Enum(TeacherAttendanceStatus, name="teacher_attendance_status_enum", native_enum=False),
        nullable=False,
    )
    calculation_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="BIOMETRIC", nullable=False)

    # Relationships
    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="attendances")
