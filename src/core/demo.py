import uuid
from typing import Dict, Any
from src.models.user import UserRole

DEMO_CREDENTIALS: Dict[str, Dict[str, Any]] = {
    "admin@fundamics.com": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "name": "Mayank Aggarwal",
        "email": "admin@fundamics.com",
        "role": UserRole.ADMIN,
        "password": "SecurePassword123!",
        "phone": "7617018888",
    },
    "admin@fundamics.in": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "name": "Mayank Aggarwal",
        "email": "admin@fundamics.in",
        "role": UserRole.ADMIN,
        "password": "SecurePassword123!",
        "phone": "7617018888",
    },
    "sunita.rao@fundamics.com": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "name": "Sunita Rao",
        "email": "sunita.rao@fundamics.com",
        "role": UserRole.TEACHER,
        "password": "TeacherSecurePass123!",
        "phone": "7800001288",
        "teacher_code": "TCH-001",
    },
    "manish.verma@fundamics.in": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "name": "Manish K. Verma",
        "email": "manish.verma@fundamics.in",
        "role": UserRole.TEACHER,
        "password": "TeacherSecurePass123!",
        "phone": "7800001288",
        "teacher_code": "TCH-001",
    },
    "rohan.sharma@example.com": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "name": "Rohan Sharma",
        "email": "rohan.sharma@example.com",
        "role": UserRole.STUDENT,
        "password": "SecurePassword123!",
        "phone": "9876543210",
        "student_code": "FND-2025-1042",
    },
    "aryan.srivastava@student.fundamics.in": {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "name": "Aryan Srivastava",
        "email": "aryan.srivastava@student.fundamics.in",
        "role": UserRole.STUDENT,
        "password": "SecurePassword123!",
        "phone": "9876543210",
        "student_code": "FND-2025-1042",
    },
}
