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

    attendance_required_hours: Optional[int] = Field(default=None, ge=1, le=24)
    timezone: Optional[str] = Field(default=None, max_length=50)
    attendance_cutoff_time: Optional[str] = Field(default=None, max_length=10)
    missing_checkout_policy: Optional[str] = Field(default=None, max_length=30)
    notifications_enabled: Optional[bool] = None


class InstituteSettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    status: str
    attendance_required_hours: int
    timezone: str
    attendance_cutoff_time: str
    missing_checkout_policy: str
    notifications_enabled: bool


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
