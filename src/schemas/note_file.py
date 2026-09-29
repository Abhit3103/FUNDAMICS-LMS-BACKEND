import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class NoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    class_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    subject_id: uuid.UUID


class NoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    title: str
    description: Optional[str] = None
    class_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    subject_id: uuid.UUID
    subject_name: Optional[str] = None
    file_id: uuid.UUID
    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    created_at: datetime


class FileRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
