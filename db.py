"""SQLite connection + idempotent migrations/seeds (safe to run repeatedly)."""
import os
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parent


def default_db_path() -> str:
    return os.environ.get("DATABASE_PATH", str(ROOT / "data" / "onboarding.db"))


def connect(path: str | None = None) -> sqlite3.Connection:
    p = path or default_db_path()
    pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply migrations/*.sql files not yet applied. Returns the list of newly applied files."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    newly = []
    for f in sorted((ROOT / "migrations").glob("*.sql")):
        if f.name in applied:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (f.name,))
        conn.commit()
        newly.append(f.name)
    return newly


def seed(conn: sqlite3.Connection) -> int:
    n = 0
    for f in sorted((ROOT / "seeds").glob("*.sql")):
        conn.executescript(f.read_text(encoding="utf-8"))
        n += 1
    conn.commit()
    return n
