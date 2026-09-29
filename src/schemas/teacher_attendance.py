import uuid
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from src.models.teacher_attendance import BiometricEventType, TeacherAttendanceStatus


class BiometricEventWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=100)
    external_event_id: str = Field(min_length=1, max_length=150)
    employee_identifier: str = Field(min_length=1, max_length=100)
    event_type: BiometricEventType
    event_at_utc: datetime


class IngestBiometricEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processed: int
    duplicates_skipped: int
    unmapped_employees: int
    message: str


class TeacherAttendanceDaySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    date: date
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    served_minutes: int
    required_minutes: int
    status: TeacherAttendanceStatus


class TeacherAttendanceOverallSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    teacher_id: uuid.UUID
    teacher_code: str
    total_days: int
    present_days: int
    absent_days: int
    half_days: int
    incomplete_days: int
    total_served_hours: float
