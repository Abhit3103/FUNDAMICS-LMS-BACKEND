import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.main import app
from src.database import get_db

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://fundamics_app:fundamics_secure_pass@localhost:5433/fundamics_test",
)

# Safety Guardrails: Guarantee tests ONLY run on local Docker fundamics_test and NEVER on Supabase or fundamics_lms
assert "supabase" not in TEST_DATABASE_URL.lower(), "ABORT: TEST_DATABASE_URL points to Supabase!"
assert "fundamics_test" in TEST_DATABASE_URL.lower(), "ABORT: TEST_DATABASE_URL must target fundamics_test!"

from sqlalchemy.pool import NullPool

engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    future=True,
    echo=False,
)

TestingSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


_DB_AVAILABLE = None


@pytest_asyncio.fixture
async def db_session():
    """Provides an isolated transaction for testing that always rolls back."""
    global _DB_AVAILABLE
    if _DB_AVAILABLE is False:
        pytest.skip("Test database on port 5433 is unavailable")

    try:
        connection = await engine.connect()
        _DB_AVAILABLE = True
    except Exception as exc:
        _DB_AVAILABLE = False
        pytest.skip(f"Test database is unavailable ({exc})")

    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def async_client(db_session):
    """FastAPI async test client with database dependency override to prevent hitting production/Supabase."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset the login rate limiter state between tests to prevent inter-test 429 errors."""
    from src.core.rate_limit import login_rate_limiter
    login_rate_limiter._history.clear()
    login_rate_limiter._last_request_time.clear()
    yield
    login_rate_limiter._history.clear()
    login_rate_limiter._last_request_time.clear()
