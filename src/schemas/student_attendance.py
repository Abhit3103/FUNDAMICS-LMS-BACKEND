import uuid
from datetime import date as dt_date, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from src.models.student_attendance import AttendanceStatus, ImportStatus


class AttendanceRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_code: str
    status: AttendanceStatus
    remarks: Optional[str] = Field(default=None, max_length=255)


class AttendanceImportPreviewRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_number: int
    student_code: str
    student_name: Optional[str] = None
    status: AttendanceStatus
    is_valid: bool
    error_message: Optional[str] = None


class AttendanceImportPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_id: uuid.UUID
    filename: str
    class_id: uuid.UUID
    batch_id: uuid.UUID
    attendance_date: date
    total_rows: int
    valid_rows: int
    error_rows: int
    preview_data: List[AttendanceImportPreviewRow]


class ConfirmAttendanceImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_id: uuid.UUID
    status: ImportStatus
    committed_rows: int
    message: str


class StudentAttendanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    student_code: str
    total_working_days: int
    present_days: int
    absent_days: int
    late_days: int
    excused_days: int
    attendance_percentage: float


class StudentAttendanceRosterItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    student_code: str
    student_name: str
    status: Optional[AttendanceStatus] = None
    remarks: Optional[str] = None
    attendance_id: Optional[uuid.UUID] = None


class StudentAttendanceRosterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: uuid.UUID
    class_name: str
    batch_id: uuid.UUID
    batch_name: str
    subject_id: uuid.UUID
    subject_name: str
    date: dt_date
    is_holiday: bool = False
    calendar_event_title: Optional[str] = None
    total_students: int
    marked_count: int
    unmarked_count: int
    students: List[StudentAttendanceRosterItem]


class StudentAttendanceSubmitItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: Optional[uuid.UUID] = None
    student_code: Optional[str] = None
    status: AttendanceStatus
    remarks: Optional[str] = Field(default=None, max_length=255)


class StudentAttendanceSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: uuid.UUID
    batch_id: uuid.UUID
    subject_id: uuid.UUID
    date: Optional[dt_date] = None
    attendance_date: Optional[dt_date] = None
    allow_holiday_override: bool = False
    records: List[StudentAttendanceSubmitItem] = Field(min_length=1)


class StudentAttendanceItemRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attendance_id: uuid.UUID
    student_id: uuid.UUID
    student_code: str
    status: AttendanceStatus
    remarks: Optional[str] = None
    source: str


class StudentAttendanceSubmitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: uuid.UUID
    batch_id: uuid.UUID
    subject_id: uuid.UUID
    date: dt_date
    total_submitted: int
    created_count: int
    updated_count: int
    message: str
    records: List[StudentAttendanceItemRecord]
