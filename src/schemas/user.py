import uuid
from datetime import date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from src.models.user import UserRole, UserStatus


class CreateStudentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    student_code: str = Field(min_length=1, max_length=50)
    class_id: uuid.UUID
    batch_id: uuid.UUID
    admission_date: date
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class UpdateStudentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=20)
    class_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    status: Optional[str] = Field(default=None, max_length=30)


class StudentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: EmailStr
    phone: Optional[str] = None
    student_code: str
    class_id: uuid.UUID
    class_name: Optional[str] = None
    batch_id: uuid.UUID
    batch_name: Optional[str] = None
    admission_date: date
    status: str


class CreateTeacherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=20)
    teacher_code: str = Field(min_length=1, max_length=50)
    biometric_employee_id: Optional[str] = Field(default=None, max_length=100)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class UpdateTeacherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=20)
    biometric_employee_id: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = Field(default=None, max_length=30)


class TeacherResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: EmailStr
    phone: Optional[str] = None
    teacher_code: str
    biometric_employee_id: Optional[str] = None
    status: str
