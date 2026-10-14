import uuid
import pytest
from httpx import AsyncClient
from src.core.security import hash_password, create_access_token
from src.models.user import User, UserRole, UserStatus
from src.models.academic import Class, Batch, Subject


@pytest.mark.asyncio
async def test_academic_board_and_crud_lifecycle(async_client: AsyncClient, db_session):
    admin = User(
        name="Admin Academic",
        email="admin_acad@fundamics.com",
        password_hash=hash_password("Admin@123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db_session.add(admin)
    await db_session.flush()
    admin_token = create_access_token(subject=str(admin.id), role=UserRole.ADMIN.value)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create classes with different boards
    c1 = await async_client.post(
        "/api/v1/admin/classes",
        headers=headers,
        json={"name": "Class 10 CBSE", "code": "C10-CBSE", "board": "CBSE", "academic_year": "2026-2027"},
    )
    assert c1.status_code == 201
    assert c1.json()["board"] == "CBSE"
    class_id = c1.json()["id"]

    c2 = await async_client.post(
        "/api/v1/admin/classes",
        headers=headers,
        json={"name": "Class 10 ICSE", "code": "C10-ICSE", "board": "ICSE", "academic_year": "2026-2027"},
    )
    assert c2.status_code == 201
    assert c2.json()["board"] == "ICSE"

    # 2. Filter classes by board
    list_cbse = await async_client.get("/api/v1/admin/classes?board=CBSE", headers=headers)
    assert list_cbse.status_code == 200
    cbse_items = list_cbse.json()
    assert all(c["board"] == "CBSE" for c in cbse_items)

    list_icse = await async_client.get("/api/v1/admin/classes?board=ICSE", headers=headers)
    assert list_icse.status_code == 200
    icse_items = list_icse.json()
    assert all(c["board"] == "ICSE" for c in icse_items)

    # 3. Update class
    update_class_res = await async_client.patch(
        f"/api/v1/admin/classes/{class_id}",
        headers=headers,
        json={"name": "Class 10 CBSE (Premier)", "academic_year": "2026-2028"},
    )
    assert update_class_res.status_code == 200
    assert update_class_res.json()["name"] == "Class 10 CBSE (Premier)"

    # 4. Create, Update, Delete Batch
    batch_res = await async_client.post(
        "/api/v1/admin/batches",
        headers=headers,
        json={"class_id": class_id, "name": "Morning Stars", "code": "MS-1", "start_time": "08:00", "end_time": "10:00"},
    )
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["id"]

    update_batch = await async_client.patch(
        f"/api/v1/admin/batches/{batch_id}",
        headers=headers,
        json={"name": "Morning Stars Advanced"},
    )
    assert update_batch.status_code == 200
    assert update_batch.json()["name"] == "Morning Stars Advanced"

    del_batch = await async_client.delete(f"/api/v1/admin/batches/{batch_id}", headers=headers)
    assert del_batch.status_code == 200

    # 5. Create, Update, Delete Subject
    sub_res = await async_client.post(
        "/api/v1/admin/subjects",
        headers=headers,
        json={"class_id": class_id, "name": "Mathematics", "code": "MTH-10"},
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    update_sub = await async_client.patch(
        f"/api/v1/admin/subjects/{sub_id}",
        headers=headers,
        json={"name": "Advanced Mathematics"},
    )
    assert update_sub.status_code == 200
    assert update_sub.json()["name"] == "Advanced Mathematics"

    del_sub = await async_client.delete(f"/api/v1/admin/subjects/{sub_id}", headers=headers)
    assert del_sub.status_code == 200

    # 6. Delete Class
    del_class = await async_client.delete(f"/api/v1/admin/classes/{class_id}", headers=headers)
    assert del_class.status_code == 200
