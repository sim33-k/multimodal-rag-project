# database connection file, everything that need db imports can get it from here. We create a single engine

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL","postgresql://sltourism_user:devpassword@localhost:5432/sltourism",)


# we have enabled prool_pre_ping because when sqlalchemy gives a connection from pool it could be dead, so we need to check if its actually alive
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


def get_engine():
    return engine


def fetch_all(sql, params=None):
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
    try:
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
        conn.close()
        return True
    except Exception:
        return False
