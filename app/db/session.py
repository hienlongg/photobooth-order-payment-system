from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Create async engine with connection pooling configured for asyncpg
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session per request.
    - Write operations (POST/PATCH/DELETE) commit explicitly within route handlers
      before responses are sent to ensure data is committed to disk before returning 201/200.
    - Handles automatic rollback on any unhandled exception.
    - Closes and returns the connection to the pool in the finally block.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
