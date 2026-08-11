from __future__ import annotations

from pathlib import Path

from app.db.session import get_pool

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def migrate() -> list[str]:
    pool = await get_pool()
    applied: list[str] = []
    async with pool.acquire() as connection:
        await connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version varchar(100) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", 684_210_731)
            known = await connection.fetch("SELECT version FROM schema_migrations")
            known_versions = {row["version"] for row in known}
            for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
                if path.name in known_versions:
                    continue
                await connection.execute(path.read_text(encoding="utf-8"))
                await connection.execute("INSERT INTO schema_migrations(version) VALUES($1)", path.name)
                applied.append(path.name)
    return applied
