from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings


def _engine_kwargs() -> dict:
    # SQLite (local dev / tests) does not benefit from pool pre-ping or recycling.
    # Postgres via Supabase Session Pooler drops idle connections; pre-ping + recycle
    # avoid handing the app a dead connection.
    if settings.database_url.startswith("sqlite"):
        return {"echo": False}
    return {"echo": False, "pool_pre_ping": True, "pool_recycle": 300}


engine = create_async_engine(settings.database_url, **_engine_kwargs())
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session
