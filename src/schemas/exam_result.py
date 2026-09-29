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
    subject_id: uuid.UUID
    marks_obtained: float = Field(ge=0.0)
    max_marks: float = Field(gt=0.0)
    grade: Optional[str] = Field(default=None, max_length=10)


class BulkEnterMarksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    marks_entries: List[EnterMarksItem]


class PublishExamResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    publish: bool = True


class ResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    exam_id: uuid.UUID
    exam_name: Optional[str] = None
    student_id: uuid.UUID
    subject_id: uuid.UUID
    subject_name: Optional[str] = None
    marks_obtained: float
    max_marks: float
    percentage: float
    grade: Optional[str] = None
    published_at: Optional[datetime] = None


class StudentExamSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: uuid.UUID
    exam_name: str
    exam_date: date
    total_marks_obtained: float
    total_max_marks: float
    overall_percentage: float
    results: List[ResultResponse]
