from fastapi import APIRouter
from src.api.v1.health import router as health_router
from src.api.v1.auth import router as auth_router
from src.api.v1.admin.users import router as admin_users_router
from src.api.v1.admin.academics import router as admin_academics_router
from src.api.v1.attendance import admin_attendance_router, student_attendance_router
from src.api.v1.biometric import integrations_router, teacher_attendance_router, admin_teacher_attendance_router
from src.api.v1.results import admin_results_router, student_results_router
from src.api.v1.notes import admin_notes_router, student_notes_router
from src.api.v1.system import admin_system_router

v1_router = APIRouter()

# Core system routes
v1_router.include_router(health_router)
v1_router.include_router(auth_router)

# Admin core routes
v1_router.include_router(admin_users_router)
v1_router.include_router(admin_academics_router)
v1_router.include_router(admin_attendance_router)
v1_router.include_router(admin_teacher_attendance_router)
v1_router.include_router(admin_results_router)
v1_router.include_router(admin_notes_router)
v1_router.include_router(admin_system_router)

# Student role-specific /me routes
v1_router.include_router(student_attendance_router)
v1_router.include_router(student_results_router)
v1_router.include_router(student_notes_router)

# Teacher role-specific /me routes
v1_router.include_router(teacher_attendance_router)

# External Integration routes
v1_router.include_router(integrations_router)
