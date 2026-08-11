from pathlib import Path

from app.db.migrations import MIGRATIONS_DIR
from app.db.session import _asyncpg_dsn


def test_database_url_is_accepted_by_asyncpg():
    assert _asyncpg_dsn("postgresql://user:pass@localhost/db") == "postgresql://user:pass@localhost/db"
    assert _asyncpg_dsn("postgresql+asyncpg://user:pass@localhost/db") == "postgresql://user:pass@localhost/db"


def test_numbered_sql_migration_exists():
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    assert files
    sql = files[0].read_text(encoding="utf-8")
    assert "CREATE TABLE user_accounts" in sql
    assert "CREATE TABLE diagnostic_runs" in sql


def test_runtime_has_no_sqlalchemy_or_alembic_imports():
    root = Path(__file__).resolve().parents[1]
    source = "\n".join(path.read_text(encoding="utf-8") for path in (root / "app").rglob("*.py"))
    assert "sqlalchemy" not in source.lower()
    assert "alembic" not in source.lower()
