import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from src.models.user import UserRole, UserStatus


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    device_info: Optional[str] = Field(default=None, max_length=255)


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    new_password: str = Field(min_length=8, max_length=128)


class StudentSelfRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    class_id: uuid.UUID
    batch_id: uuid.UUID


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    email: Optional[EmailStr] = None


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=20)


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: UserRole
    status: UserStatus
    student_id: Optional[uuid.UUID] = None
    teacher_id: Optional[uuid.UUID] = None
    student_code: Optional[str] = None
    teacher_code: Optional[str] = None
