import uuid
from datetime import date
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
