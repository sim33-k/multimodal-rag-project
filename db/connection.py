"""Single place where the Postgres connection is configured.

Everything that touches the database imports from here so the DATABASE_URL is
read once and the engine is shared rather than rebuilt per query.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sltourism_user:devpassword@localhost:5432/sltourism",
)

# pool_pre_ping avoids handing out connections that Postgres has already closed,
# which happens easily when the Docker container is restarted mid-session.
_engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


def get_engine() -> Engine:
    return _engine


def fetch_all(sql: str, params: dict | None = None) -> list[dict]:
    """Run a read query and return rows as plain dicts.

    Returning dicts rather than SQLAlchemy Row objects keeps the retrieval layer
    free of ORM types, so results can be merged and JSON-serialised directly.
    """
    with _engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings()]


def ping() -> bool:
    """True if the database is reachable. Used by the API health check."""
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
