# Database connection. Everything that needs the DB imports from here so we
# only build the engine once.

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

# pool_pre_ping stops us getting a dead connection after the docker container
# gets restarted, which happened a lot while developing
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


def get_engine():
    return engine


def fetch_all(sql, params=None):
    # returns rows as normal dicts so the rest of the code doesn't have to deal
    # with sqlalchemy Row objects
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        rows = []
        for row in result.mappings():
            rows.append(dict(row))
        return rows


def ping():
    # used by /health
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
