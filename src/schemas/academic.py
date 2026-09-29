import uuid
from datetime import time
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class CreateClassRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)
    academic_year: str = Field(min_length=4, max_length=20)


class UpdateClassRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    academic_year: Optional[str] = Field(default=None, min_length=4, max_length=20)
    status: Optional[str] = Field(default=None, max_length=30)


class ClassResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    academic_year: str
    status: str


class CreateBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)
    start_time: time
    end_time: time


class UpdateBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    status: Optional[str] = Field(default=None, max_length=30)


class BatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    name: str
    code: str
    start_time: time
    end_time: time
    status: str


class CreateSubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)


class UpdateSubjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    status: Optional[str] = Field(default=None, max_length=30)


class SubjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    name: str
    code: str
    status: str
