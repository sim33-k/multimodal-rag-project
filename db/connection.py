# Database connection. Everything that needs the DB imports from here so we only
# build the engine once.

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sltourism_user:devpassword@localhost:5432/sltourism",
)

# pool_pre_ping stops us getting handed a dead connection after the docker
# container gets restarted, which happened a lot while building this
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


def get_engine():
    return engine


def fetch_all(sql, params=None):
    # gives back normal dicts so the rest of the code doesn't have to deal with
    # sqlalchemy Row objects
    if params is None:
        params = {}

    conn = engine.connect()
    try:
        result = conn.execute(text(sql), params)
        rows = []
        for row in result.mappings():
            rows.append(dict(row))
        return rows
    finally:
        conn.close()


def ping():
    # used by /health
    try:
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
        conn.close()
        return True
    except Exception:
        return False
