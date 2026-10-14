import uuid
from datetime import date, datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from src.models.system import CalendarEventType


class CalendarEventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=150)
    date: date
    type: CalendarEventType
    applies_to: str = Field(default="ALL", max_length=50)
    class_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None


class CalendarEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    title: str
    date: date
    type: CalendarEventType
    applies_to: str
    class_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None


class InstituteSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institute_status: Optional[str] = Field(default=None, max_length=30)
    erp_messaging_enabled: Optional[bool] = None
    status: Optional[str] = Field(default=None, max_length=30)
    attendance_required_hours: Optional[int] = Field(default=None, ge=1, le=24)
    timezone: Optional[str] = Field(default=None, max_length=50)
    attendance_cutoff_time: Optional[str] = Field(default=None, max_length=10)
    missing_checkout_policy: Optional[str] = Field(default=None, max_length=30)
    notifications_enabled: Optional[bool] = None


class InstituteSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    status: str
    institute_status: str
    erp_messaging_enabled: bool
    attendance_required_hours: int
    timezone: str
    attendance_cutoff_time: str
    missing_checkout_policy: str
    notifications_enabled: bool


class NoticeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    target_audience: str = Field(default="ALL", max_length=50)
    class_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    priority: str = Field(default="NORMAL", max_length=30)
    attachment_file_id: Optional[uuid.UUID] = None
    expires_at: Optional[datetime] = None


class NoticeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1)
    target_audience: Optional[str] = Field(default=None, max_length=50)
    class_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    priority: Optional[str] = Field(default=None, max_length=30)
    attachment_file_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class NoticeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    target_audience: str
    class_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    priority: str
    attachment_file_id: Optional[uuid.UUID] = None
    is_active: bool
    published_at: datetime
    expires_at: Optional[datetime] = None
    created_by: uuid.UUID


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    before_json: Optional[Dict[str, Any]] = None
    after_json: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    created_at: datetime
