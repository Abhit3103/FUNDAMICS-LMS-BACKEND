import enum
import uuid
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Date, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import TimeStampedUUIDModel


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"


class User(TimeStampedUUIDModel):
    __tablename__ = "users"

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status_enum", native_enum=False),
        default=UserStatus.PENDING_VERIFICATION,
        nullable=False,
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 1-to-1 relationships
    student: Mapped[Optional["Student"]] = relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    teacher: Mapped[Optional["Teacher"]] = relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")
    auth_sessions: Mapped[List["AuthSession"]] = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")


class Student(TimeStampedUUIDModel):
    __tablename__ = "students"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    student_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    admission_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="student")
    current_class: Mapped["Class"] = relationship("Class", foreign_keys=[class_id])
    current_batch: Mapped["Batch"] = relationship("Batch", foreign_keys=[batch_id])
    enrollments: Mapped[List["Enrollment"]] = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")
    attendances: Mapped[List["StudentAttendance"]] = relationship("StudentAttendance", back_populates="student")
    results: Mapped[List["Result"]] = relationship("Result", back_populates="student")


class Teacher(TimeStampedUUIDModel):
    __tablename__ = "teachers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    teacher_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    biometric_employee_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="teacher")
    biometric_events: Mapped[List["BiometricEvent"]] = relationship("BiometricEvent", back_populates="teacher")
    attendances: Mapped[List["TeacherAttendance"]] = relationship("TeacherAttendance", back_populates="teacher")
