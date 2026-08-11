from __future__ import annotations

import asyncpg

from app.core.config import get_settings

_pool: asyncpg.Pool | None = None


def _asyncpg_dsn(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


async def get_pool() -> asyncpg.Pool:
    global _pool
    settings = get_settings()
    if not settings.database_enabled:
        raise RuntimeError("데이터베이스 기능이 비활성화되어 있습니다.")
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=_asyncpg_dsn(settings.database_url),
            min_size=1,
            max_size=settings.database_pool_size + settings.database_max_overflow,
            timeout=settings.database_pool_timeout_seconds,
            command_timeout=settings.database_statement_timeout_ms / 1000,
        )
    return _pool


async def database_ready() -> bool:
    if not get_settings().database_enabled:
        return False
    try:
        pool = await get_pool()
        async with pool.acquire() as connection:
            return await connection.fetchval("SELECT 1") == 1
    except Exception:
        return False


async def dispose_engine() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
    _pool = None
