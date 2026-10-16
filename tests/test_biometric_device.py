import uuid
import pytest
from datetime import datetime, date, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.teacher_attendance import (
    BiometricDevice,
    BiometricEvent,
    BiometricEventType,
    TeacherAttendance,
    TeacherAttendanceStatus,
)
from src.models.user import Teacher, User, UserRole, UserStatus
from src.core.security import hash_password
from src.services.biometric_service import biometric_service
from src.services.biometric_adapter import (
    SecureyeNativeWebhookAdapter,
    SecureyeSB8CBLocalBridgeAdapter,
)


async def create_test_teacher(db: AsyncSession, name: str, email: str, bio_id: str) -> Teacher:
    user = User(
        role=UserRole.TEACHER,
        name=name,
        email=email,
        password_hash=hash_password("TeacherSecurePass123!"),
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.flush()

    teacher = Teacher(
        user_id=user.id,
        teacher_code=f"TCH-{uuid.uuid4().hex[:4].upper()}",
        biometric_employee_id=bio_id,
        status="ACTIVE",
    )
    db.add(teacher)
    await db.flush()
    return teacher


async def create_test_device(db: AsyncSession, dev_id: str, secret: str, status: str = "ACTIVE") -> BiometricDevice:
    device = BiometricDevice(
        external_device_id=dev_id,
        name="Main Campus Biometric S-B8CB",
        model="Secureye S-B8CB",
        secret_reference=secret,
        status=status,
    )
    db.add(device)
    await db.flush()
    return device


@pytest.mark.asyncio
async def test_biometric_single_event_payload(async_client: AsyncClient, db_session: AsyncSession):
    """Test that endpoint accepts a single event JSON object and processes it correctly."""
    secret = "secret-single-evt"
    dev_id = f"SB8CB-TEST-{uuid.uuid4().hex[:6]}"
    await create_test_device(db_session, dev_id, secret)
    teacher = await create_test_teacher(db_session, "Teacher Alpha", f"alpha_{uuid.uuid4().hex[:4]}@test.local", "BIO-A1")

    payload = {
        "device_id": dev_id,
        "external_event_id": f"EVT-{uuid.uuid4().hex[:8]}",
        "employee_identifier": teacher.biometric_employee_id,
        "event_type": "IN",
        "event_at_utc": "2026-10-16T08:30:00Z",
    }

    resp = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=payload,
        headers={"x-device-secret": secret},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 1
    assert data["duplicates_skipped"] == 0
    assert data["unmapped_employees"] == 0


@pytest.mark.asyncio
async def test_biometric_device_id_mismatch_rejected(async_client: AsyncClient, db_session: AsyncSession):
    """Test that submitting an event with a device_id different from the authenticated device is rejected with 400."""
    secret = "secret-mismatch"
    real_dev_id = f"SB8CB-REAL-{uuid.uuid4().hex[:6]}"
    await create_test_device(db_session, real_dev_id, secret)

    payload = [
        {
            "device_id": "SB8CB-SPOOFED-DEVICE",
            "external_event_id": f"EVT-{uuid.uuid4().hex[:8]}",
            "employee_identifier": "BIO-001",
            "event_type": "IN",
            "event_at_utc": "2026-10-16T08:30:00Z",
        }
    ]

    resp = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=payload,
        headers={"x-device-secret": secret},
    )
    assert resp.status_code == 400
    assert "Device ID mismatch" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_biometric_unknown_teacher_identifier(async_client: AsyncClient, db_session: AsyncSession):
    """Test that punches for an unmapped employee ID are recorded with teacher_id=None and unmapped count."""
    secret = "secret-unmapped"
    dev_id = f"SB8CB-DEV-{uuid.uuid4().hex[:6]}"
    device = await create_test_device(db_session, dev_id, secret)

    evt_id = f"EVT-UNMAPPED-{uuid.uuid4().hex[:8]}"
    payload = [
        {
            "device_id": dev_id,
            "external_event_id": evt_id,
            "employee_identifier": "UNKNOWN-STUDENT-OR-VISITOR",
            "event_type": "IN",
            "event_at_utc": "2026-10-16T09:00:00Z",
        }
    ]

    resp = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=payload,
        headers={"x-device-secret": secret},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 1
    assert data["unmapped_employees"] == 1

    # Verify event stored with teacher_id = None
    ev_stmt = select(BiometricEvent).where(
        BiometricEvent.device_id == device.id,
        BiometricEvent.external_event_id == evt_id,
    )
    ev_res = await db_session.execute(ev_stmt)
    ev = ev_res.scalar_one_or_none()
    assert ev is not None
    assert ev.teacher_id is None


@pytest.mark.asyncio
async def test_biometric_intra_batch_duplicate(async_client: AsyncClient, db_session: AsyncSession):
    """Test that multiple identical events within the same request payload are deduplicated safely."""
    secret = "secret-intra"
    dev_id = f"SB8CB-INTRA-{uuid.uuid4().hex[:6]}"
    await create_test_device(db_session, dev_id, secret)
    teacher = await create_test_teacher(db_session, "Teacher Beta", f"beta_{uuid.uuid4().hex[:4]}@test.local", "BIO-B1")

    common_evt_id = f"EVT-DUAL-{uuid.uuid4().hex[:8]}"
    payload = [
        {
            "device_id": dev_id,
            "external_event_id": common_evt_id,
            "employee_identifier": teacher.biometric_employee_id,
            "event_type": "IN",
            "event_at_utc": "2026-10-16T08:30:00Z",
        },
        {
            "device_id": dev_id,
            "external_event_id": common_evt_id,
            "employee_identifier": teacher.biometric_employee_id,
            "event_type": "IN",
            "event_at_utc": "2026-10-16T08:30:00Z",
        },
    ]

    resp = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=payload,
        headers={"x-device-secret": secret},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 1
    assert data["duplicates_skipped"] == 1


@pytest.mark.asyncio
async def test_biometric_naive_timestamp_normalized(async_client: AsyncClient, db_session: AsyncSession):
    """Test that a naive timestamp is parsed and normalized to UTC."""
    secret = "secret-naive-time"
    dev_id = f"SB8CB-TIME-{uuid.uuid4().hex[:6]}"
    await create_test_device(db_session, dev_id, secret)
    teacher = await create_test_teacher(db_session, "Teacher Gamma", f"gamma_{uuid.uuid4().hex[:4]}@test.local", "BIO-G1")

    payload = {
        "device_id": dev_id,
        "external_event_id": f"EVT-TIME-{uuid.uuid4().hex[:8]}",
        "employee_identifier": teacher.biometric_employee_id,
        "event_type": "IN",
        "event_at_utc": "2026-10-16T08:30:00",  # naive ISO without Z
    }

    resp = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=payload,
        headers={"x-device-secret": secret},
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] == 1


@pytest.mark.asyncio
async def test_biometric_idempotent_recalculation(db_session: AsyncSession):
    """Test that calculate_teacher_daily is idempotent and updates existing records without IntegrityError."""
    dev_id = f"SB8CB-CALC-{uuid.uuid4().hex[:6]}"
    device = await create_test_device(db_session, dev_id, "calc-secret")
    teacher = await create_test_teacher(db_session, "Teacher Delta", f"delta_{uuid.uuid4().hex[:4]}@test.local", "BIO-D1")

    target_date = date(2026, 10, 16)
    # IN punch at 08:30 IST (03:00 UTC)
    in_time = datetime(2026, 10, 16, 3, 0, 0, tzinfo=timezone.utc)
    # OUT punch at 17:00 IST (11:30 UTC) - 8.5 hours
    out_time = datetime(2026, 10, 16, 11, 30, 0, tzinfo=timezone.utc)

    db_session.add(
        BiometricEvent(
            device_id=device.id,
            external_event_id=f"EVT-IN-{uuid.uuid4().hex[:6]}",
            employee_identifier=teacher.biometric_employee_id,
            teacher_id=teacher.id,
            event_type=BiometricEventType.IN,
            event_at_utc=in_time,
            received_at=in_time,
        )
    )
    db_session.add(
        BiometricEvent(
            device_id=device.id,
            external_event_id=f"EVT-OUT-{uuid.uuid4().hex[:6]}",
            employee_identifier=teacher.biometric_employee_id,
            teacher_id=teacher.id,
            event_type=BiometricEventType.OUT,
            event_at_utc=out_time,
            received_at=out_time,
        )
    )
    await db_session.flush()

    # 1. First calculation
    summary1 = await biometric_service.calculate_teacher_daily(
        db=db_session,
        teacher_id=teacher.id,
        target_date=target_date,
    )
    assert summary1.status == TeacherAttendanceStatus.PRESENT
    assert summary1.served_minutes == 510  # 8.5 hours * 60

    # 2. Second calculation for same day (idempotent recalculation test)
    summary2 = await biometric_service.calculate_teacher_daily(
        db=db_session,
        teacher_id=teacher.id,
        target_date=target_date,
    )
    assert summary2.status == TeacherAttendanceStatus.PRESENT
    assert summary2.served_minutes == 510

    # Verify calculation_version was incremented
    rec = (await db_session.execute(
        select(TeacherAttendance).where(
            TeacherAttendance.teacher_id == teacher.id,
            TeacherAttendance.date == target_date,
        )
    )).scalar_one()
    assert rec.calculation_version == 2


@pytest.mark.asyncio
async def test_biometric_half_day_and_incomplete_status(db_session: AsyncSession):
    """Test teacher attendance status determination for half-day and incomplete punches."""
    dev_id = f"SB8CB-STAT-{uuid.uuid4().hex[:6]}"
    device = await create_test_device(db_session, dev_id, "stat-secret")
    teacher = await create_test_teacher(db_session, "Teacher Epsilon", f"eps_{uuid.uuid4().hex[:4]}@test.local", "BIO-E1")

    # Incomplete: Only IN punch
    in_time = datetime(2026, 10, 15, 3, 30, 0, tzinfo=timezone.utc)
    db_session.add(
        BiometricEvent(
            device_id=device.id,
            external_event_id=f"EVT-INC-{uuid.uuid4().hex[:6]}",
            employee_identifier=teacher.biometric_employee_id,
            teacher_id=teacher.id,
            event_type=BiometricEventType.IN,
            event_at_utc=in_time,
            received_at=in_time,
        )
    )
    await db_session.flush()

    inc_summary = await biometric_service.calculate_teacher_daily(
        db=db_session,
        teacher_id=teacher.id,
        target_date=date(2026, 10, 15),
    )
    assert inc_summary.status == TeacherAttendanceStatus.INCOMPLETE

    # Half Day: Served ~4 hours (240 mins) vs 480 required
    out_time_half = in_time + timedelta(hours=4, minutes=5)
    db_session.add(
        BiometricEvent(
            device_id=device.id,
            external_event_id=f"EVT-HALF-{uuid.uuid4().hex[:6]}",
            employee_identifier=teacher.biometric_employee_id,
            teacher_id=teacher.id,
            event_type=BiometricEventType.OUT,
            event_at_utc=out_time_half,
            received_at=out_time_half,
        )
    )
    await db_session.flush()

    half_summary = await biometric_service.calculate_teacher_daily(
        db=db_session,
        teacher_id=teacher.id,
        target_date=date(2026, 10, 15),
    )
    assert half_summary.status == TeacherAttendanceStatus.HALF_DAY


def test_biometric_adapters():
    """Test transport adapter normalization for native webhook and LAN bridge payloads."""
    # 1. Native webhook adapter
    native_adapter = SecureyeNativeWebhookAdapter()
    raw_native = {
        "external_event_id": "NAT-001",
        "employee_identifier": "EMP-99",
        "event_type": "IN",
        "event_at_utc": "2026-10-16T08:00:00Z",
    }
    norm_native = native_adapter.normalize_event(raw_native, device_id="DEV-NATIVE-01")
    assert norm_native.device_id == "DEV-NATIVE-01"
    assert norm_native.employee_identifier == "EMP-99"
    assert norm_native.event_type == BiometricEventType.IN

    # 2. Secureye S-B8CB Local Bridge adapter
    bridge_adapter = SecureyeSB8CBLocalBridgeAdapter(local_timezone_offset_hours=5.5)
    raw_bridge = {
        "RecordID": 1042,
        "EnrollNumber": "EMP-77",
        "InOutMode": 1,  # OUT
        "Time": "2026-10-16 17:30:00",
    }
    norm_bridge = bridge_adapter.normalize_event(raw_bridge, device_id="DEV-BRIDGE-01")
    assert norm_bridge.device_id == "DEV-BRIDGE-01"
    assert norm_bridge.external_event_id == "SB8CB-DEV-BRIDGE-01-1042"
    assert norm_bridge.employee_identifier == "EMP-77"
    assert norm_bridge.event_type == BiometricEventType.OUT
    # 17:30 IST is 12:00 UTC
    assert norm_bridge.event_at_utc.hour == 12
    assert norm_bridge.event_at_utc.minute == 0


@pytest.mark.asyncio
async def test_admin_device_crud_lifecycle(async_client: AsyncClient, db_session: AsyncSession):
    """Test admin endpoints: register, list, update device, and verify non-admin forbidden."""
    from src.core.security import create_access_token

    # 1. Create admin user
    admin_user = User(
        role=UserRole.ADMIN,
        name="Admin Bio",
        email=f"admin_{uuid.uuid4().hex[:4]}@test.local",
        password_hash=hash_password("AdminSecurePass123!"),
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(admin_user)

    # Create teacher user (non-admin)
    teacher_user = User(
        role=UserRole.TEACHER,
        name="Teacher Reg",
        email=f"tch_{uuid.uuid4().hex[:4]}@test.local",
        password_hash=hash_password("TeacherPass123!"),
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(teacher_user)
    await db_session.flush()

    admin_token = create_access_token(subject=str(admin_user.id), role=admin_user.role.value)
    teacher_token = create_access_token(subject=str(teacher_user.id), role=teacher_user.role.value)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}

    dev_ext_id = f"SB8CB-CRUD-{uuid.uuid4().hex[:6]}"
    reg_payload = {
        "external_device_id": dev_ext_id,
        "name": "Gate 1 Secureye S-B8CB",
        "model": "Secureye S-B8CB",
        "secret": "my-super-secure-shared-secret-12345",
    }

    # 2. Non-admin forbidden
    resp_forbidden = await async_client.post(
        "/api/v1/admin/biometric-devices",
        json=reg_payload,
        headers=teacher_headers,
    )
    assert resp_forbidden.status_code == 403

    # 3. Admin register success (201)
    resp_create = await async_client.post(
        "/api/v1/admin/biometric-devices",
        json=reg_payload,
        headers=admin_headers,
    )
    assert resp_create.status_code == 201
    created_data = resp_create.json()
    assert created_data["external_device_id"] == dev_ext_id
    assert created_data["name"] == "Gate 1 Secureye S-B8CB"
    assert created_data["status"] == "ACTIVE"
    assert "secret" not in created_data  # Secret never exposed
    dev_id = created_data["id"]

    # 4. Duplicate external_device_id rejected (409 Conflict)
    resp_dup = await async_client.post(
        "/api/v1/admin/biometric-devices",
        json=reg_payload,
        headers=admin_headers,
    )
    assert resp_dup.status_code == 409

    # 5. List devices (200)
    resp_list = await async_client.get(
        "/api/v1/admin/biometric-devices",
        headers=admin_headers,
    )
    assert resp_list.status_code == 200
    devices = resp_list.json()
    assert any(d["id"] == dev_id for d in devices)

    # 6. Update device status to INACTIVE & rotate secret (200)
    resp_patch = await async_client.patch(
        f"/api/v1/admin/biometric-devices/{dev_id}",
        json={"status": "INACTIVE", "secret": "rotated-new-secret-99999"},
        headers=admin_headers,
    )
    assert resp_patch.status_code == 200
    patched_data = resp_patch.json()
    assert patched_data["status"] == "INACTIVE"
    assert "secret" not in patched_data

    # 7. Ingest using old secret or while inactive is rejected (401)
    test_evt = {
        "device_id": dev_ext_id,
        "external_event_id": f"EVT-REJ-{uuid.uuid4().hex[:6]}",
        "employee_identifier": "EMP-001",
        "event_type": "IN",
        "event_at_utc": "2026-10-16T08:00:00Z",
    }
    resp_ingest_old = await async_client.post(
        "/api/v1/integrations/biometric/secureye/events",
        json=test_evt,
        headers={"x-device-secret": "my-super-secure-shared-secret-12345"},
    )
    assert resp_ingest_old.status_code == 401
