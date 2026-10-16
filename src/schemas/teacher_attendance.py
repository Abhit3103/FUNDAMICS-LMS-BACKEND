import uuid
from datetime import datetime, date, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, field_validator
from src.models.teacher_attendance import BiometricEventType, TeacherAttendanceStatus


class BiometricEventWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=100)
    external_event_id: str = Field(min_length=1, max_length=150)
    employee_identifier: str = Field(min_length=1, max_length=100)
    event_type: BiometricEventType
    event_at_utc: datetime
    raw_reference: Optional[str] = Field(default=None, max_length=500)

    @field_validator("event_at_utc", mode="after")
    @classmethod
    def ensure_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


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


class TeacherAttendanceRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    teacher_id: uuid.UUID
    teacher_name: Optional[str] = None
    teacher_code: Optional[str] = None
    date: date
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    served_minutes: int
    required_minutes: int
    status: TeacherAttendanceStatus


class TeacherAttendanceReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    total_records: int
    present_count: int
    absent_count: int
    half_day_count: int
    incomplete_count: int
    total_hours_served: float
    teacher_summaries: List[TeacherAttendanceOverallSummary]


class BiometricDeviceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_device_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    model: Optional[str] = Field(default="Secureye S-B8CB", max_length=100)
    secret: str = Field(min_length=8, max_length=255)


class BiometricDeviceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    secret: Optional[str] = Field(default=None, min_length=8, max_length=255)


class BiometricDeviceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    external_device_id: str
    name: str
    model: Optional[str] = None
    status: str
    last_seen_at: Optional[datetime] = None
    created_at: datetime
