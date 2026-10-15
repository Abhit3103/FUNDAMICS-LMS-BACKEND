import uuid
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class CreateExamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    name: str = Field(min_length=1, max_length=150)
    date: date


class ExamResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    name: str
    date: date
    status: str


class EnterMarksItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    subject_id: Optional[uuid.UUID] = None
    marks_obtained: float = Field(ge=0.0)
    max_marks: float = Field(gt=0.0)
    grade: Optional[str] = Field(default=None, max_length=10)
    remarks: Optional[str] = Field(default=None, max_length=500)
    document_file_id: Optional[uuid.UUID] = None
    file_id: Optional[uuid.UUID] = None


class BulkEnterMarksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    marks_entries: List[EnterMarksItem]


class PublishExamResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    publish: bool = True


class MapResultDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: Optional[uuid.UUID] = None
    document_file_id: Optional[uuid.UUID] = None


class DirectStudentResultDocumentMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    student_id: uuid.UUID
    file_id: uuid.UUID
    subject_id: Optional[uuid.UUID] = None
    remarks: Optional[str] = Field(default=None, max_length=500)


class ResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    exam_name: Optional[str] = None
    student_id: uuid.UUID
    student_name: Optional[str] = None
    student_code: Optional[str] = None
    subject_id: uuid.UUID
    subject_name: Optional[str] = None
    marks_obtained: float
    max_marks: float
    percentage: float
    grade: Optional[str] = None
    remarks: Optional[str] = None
    published_at: Optional[datetime] = None
    document_file_id: Optional[uuid.UUID] = None
    document_filename: Optional[str] = None
    has_document: bool = False


class StudentExamSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    exam_name: str
    exam_date: date
    total_marks_obtained: float
    total_max_marks: float
    overall_percentage: float
    results: List[ResultResponse]


class ExamDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    class_name: Optional[str] = None
    batch_id: Optional[uuid.UUID] = None
    batch_name: Optional[str] = None
    name: str
    date: date
    status: str
    results: List[ResultResponse] = []
