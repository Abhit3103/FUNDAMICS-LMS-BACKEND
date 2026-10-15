"""
Seed script to insert demo Admin, Teacher, and Student accounts into PostgreSQL.
Usage:
    python scripts/seed_demo_data.py
"""

import asyncio
import os
import sys
import uuid
from datetime import date, time, datetime, timezone

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.core.security import hash_password
from src.core.demo import DEMO_CREDENTIALS
from src.models.user import User, UserStatus, UserRole, Student, Teacher
from src.models.academic import Class, Batch, Enrollment


async def seed():
    async with AsyncSessionLocal() as session:
        print("Seeding demo accounts and academic structures into PostgreSQL...")

        # 1. Create or fetch a demo Class & Batch
        class_stmt = select(Class).where(Class.code == "CLS-12-SCI")
        res_class = await session.execute(class_stmt)
        demo_class = res_class.scalar_one_or_none()

        if not demo_class:
            demo_class = Class(
                id=uuid.uuid4(),
                name="Class XII - Science",
                code="CLS-12-SCI",
                board="ISC",
                academic_year="2025-2026",
                status="ACTIVE",
            )
            session.add(demo_class)
            await session.flush()
            print("  + Created demo Class: CLS-12-SCI")

        batch_stmt = select(Batch).where(Batch.code == "BATCH-2025-A")
        res_batch = await session.execute(batch_stmt)
        demo_batch = res_batch.scalar_one_or_none()

        if not demo_batch:
            demo_batch = Batch(
                id=uuid.uuid4(),
                class_id=demo_class.id,
                name="Batch A (Morning Flagship)",
                code="BATCH-2025-A",
                start_time=time(9, 0),
                end_time=time(11, 0),
                status="ACTIVE",
            )
            session.add(demo_batch)
            await session.flush()
            print("  + Created demo Batch: BATCH-2025-A")

        # 2. Seed Demo Users & Reset Existing User Passwords
        # Add primary test accounts if not in DEMO_CREDENTIALS
        all_accounts = dict(DEMO_CREDENTIALS)
        all_accounts.update({
            "admin@fundamics.com": {
                "name": "Admin Mayank",
                "email": "admin@fundamics.com",
                "role": UserRole.ADMIN,
                "password": "SecurePassword123!",
                "phone": "7617018888",
            },
            "teacher@fundamics.com": {
                "name": "Teacher Demo",
                "email": "teacher@fundamics.com",
                "role": UserRole.TEACHER,
                "password": "SecurePassword123!",
                "phone": "7800001288",
                "teacher_code": "TCH-DEMO-01",
            },
            "student@fundamics.com": {
                "name": "Student Demo",
                "email": "student@fundamics.com",
                "role": UserRole.STUDENT,
                "password": "SecurePassword123!",
                "phone": "9876543210",
                "student_code": "STU-DEMO-01",
            },
        })

        for email, demo in all_accounts.items():
            stmt = select(User).where(User.email == email)
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()

            if existing:
                existing.password_hash = hash_password(demo["password"])
                existing.status = UserStatus.ACTIVE
                existing.email_verified_at = datetime.now(timezone.utc)
                print(f"  [UPDATED] User {email} password reset to: {demo['password']}")
                continue

            user_id = uuid.uuid4()
            user = User(
                id=user_id,
                name=demo["name"],
                email=demo["email"],
                phone=demo.get("phone"),
                password_hash=hash_password(demo["password"]),
                role=demo["role"],
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.flush()

            if demo["role"] == UserRole.TEACHER:
                t_code = demo.get("teacher_code") or f"TCH-{uuid.uuid4().hex[:4].upper()}"
                teacher = Teacher(
                    user_id=user.id,
                    teacher_code=t_code,
                    status="ACTIVE",
                )
                session.add(teacher)

            elif demo["role"] == UserRole.STUDENT:
                s_code = demo.get("student_code") or f"STU-{uuid.uuid4().hex[:4].upper()}"
                student = Student(
                    user_id=user.id,
                    student_code=s_code,
                    class_id=demo_class.id,
                    batch_id=demo_batch.id,
                    admission_date=date.today(),
                    status="ACTIVE",
                )
                session.add(student)
                await session.flush()

                enrollment = Enrollment(
                    student_id=student.id,
                    class_id=demo_class.id,
                    batch_id=demo_batch.id,
                    start_date=date.today(),
                    academic_year="2025-2026",
                    status="ACTIVE",
                )
                session.add(enrollment)

            print(f"  + Created {demo['role'].value}: {email} (passcode: {demo['password']})")

        await session.commit()
        print("[OK] Demo accounts seeded and passwords configured successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
