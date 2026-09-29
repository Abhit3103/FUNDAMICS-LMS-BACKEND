import uuid
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Numeric, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import TimeStampedUUIDModel


class Exam(TimeStampedUUIDModel):
    __tablename__ = "exams"

    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="SCHEDULED", nullable=False)

    # Relationships
    class_rel: Mapped["Class"] = relationship("Class", back_populates="exams")
    results: Mapped[List["Result"]] = relationship("Result", back_populates="exam", cascade="all, delete-orphan")


class Result(TimeStampedUUIDModel):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", "subject_id", name="uq_result_exam_student_subject"),
    )

    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    marks_obtained: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    max_marks: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    grade: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    exam: Mapped["Exam"] = relationship("Exam", back_populates="results")
    student: Mapped["Student"] = relationship("Student", back_populates="results")
    subject: Mapped["Subject"] = relationship("Subject", back_populates="results")
