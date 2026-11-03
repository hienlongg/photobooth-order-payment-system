import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.machine import Machine
from app.models.package import Package
from app.models.tenant import Tenant
from app.models.user import User


def _resolve_test_database_url() -> URL:
    """Test DB URL; refuses to run against anything that isn't clearly a test database."""
    raw = settings.TEST_DATABASE_URL or make_url(settings.SQLALCHEMY_DATABASE_URI).set(
        database=f"{settings.POSTGRES_DB}_test"
    ).render_as_string(hide_password=False)
    url = make_url(raw)
    dev_url = make_url(settings.SQLALCHEMY_DATABASE_URI)
    if (
        not url.database
        or not url.database.endswith("_test")
        or (url.host, url.port, url.database)
        == (dev_url.host, dev_url.port, dev_url.database)
    ):
        raise RuntimeError(
            f"Refusing to run tests against database '{url.database}': tests drop all "
            "tables. Set TEST_DATABASE_URL to a dedicated database whose name ends in "
            "'_test' (and differs from the dev database)."
        )
    return url


TEST_DATABASE_URL = _resolve_test_database_url()


_test_db_ready = False


async def ensure_test_database() -> None:
    """Creates the dedicated test database on the server if it doesn't exist yet."""
    global _test_db_ready
    if _test_db_ready:
        return
    admin_engine = create_async_engine(
        TEST_DATABASE_URL.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": TEST_DATABASE_URL.database},
            )
            if not exists:
                await conn.execute(
                    text(f'CREATE DATABASE "{TEST_DATABASE_URL.database}"')
                )
    finally:
        await admin_engine.dispose()
    _test_db_ready = True


# Use NullPool in tests to prevent asyncpg connections from being shared across closed event loops
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(autouse=True)
async def init_test_db(request):
    """Initializes tables for DB-dependent integration tests."""
    # Skip DB initialization for unit test modules that don't need database fixtures
    if (
        "db_session" not in request.fixturenames
        and "client" not in request.fixturenames
        and "seed_data" not in request.fixturenames
    ):
        yield
        return

    await ensure_test_database()

    # Apply override for FastAPI dependency
    app.dependency_overrides[get_db] = override_get_db

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def seed_data(db_session: AsyncSession) -> dict:
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Test Photobooth Co.",
        code="TEST_BOOTH",
        is_active=True,
    )
    db_session.add(tenant)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        username="test_admin",
        hashed_password=get_password_hash("TestPass123!"),
        full_name="Admin Tester",
        role="admin",
        is_active=True,
    )
    machine = Machine(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_code="BOOTH-TEST-01",
        name="Test Booth 1",
        location="Test Mall",
        status="online",
        is_active=True,
    )
    package = Package(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Test 4-Cut",
        price_vnd=70000,
        duration_seconds=300,
        is_active=True,
    )
    db_session.add_all([user, machine, package])
    await db_session.commit()

    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        role=user.role,
    )

    return {
        "tenant": tenant,
        "user": user,
        "machine": machine,
        "package": package,
        "token": token,
    }


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
