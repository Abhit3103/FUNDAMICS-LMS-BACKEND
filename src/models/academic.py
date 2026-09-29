import uuid
from datetime import date, time
from typing import Optional, List
from sqlalchemy import String, Date, Time, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import TimeStampedUUIDModel


class Class(TimeStampedUUIDModel):
    __tablename__ = "classes"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    # Relationships
    batches: Mapped[List["Batch"]] = relationship("Batch", back_populates="class_rel", cascade="all, delete-orphan")
    subjects: Mapped[List["Subject"]] = relationship("Subject", back_populates="class_rel", cascade="all, delete-orphan")
    enrollments: Mapped[List["Enrollment"]] = relationship("Enrollment", back_populates="class_rel")
    exams: Mapped[List["Exam"]] = relationship("Exam", back_populates="class_rel")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="class_rel")


class Batch(TimeStampedUUIDModel):
    __tablename__ = "batches"
    __table_args__ = (
        UniqueConstraint("class_id", "code", name="uq_batch_class_code"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    # Relationships
    class_rel: Mapped["Class"] = relationship("Class", back_populates="batches")
    enrollments: Mapped[List["Enrollment"]] = relationship("Enrollment", back_populates="batch_rel")


class Subject(TimeStampedUUIDModel):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("class_id", "code", name="uq_subject_class_code"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    # Relationships
    class_rel: Mapped["Class"] = relationship("Class", back_populates="subjects")
    results: Mapped[List["Result"]] = relationship("Result", back_populates="subject")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="subject")


class Enrollment(TimeStampedUUIDModel):
    __tablename__ = "enrollments"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    # Relationships
    student: Mapped["Student"] = relationship("Student", back_populates="enrollments")
    class_rel: Mapped["Class"] = relationship("Class", back_populates="enrollments")
    batch_rel: Mapped["Batch"] = relationship("Batch", back_populates="enrollments")
