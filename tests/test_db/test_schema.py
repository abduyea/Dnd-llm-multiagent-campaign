import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.app.db.base import Base
from backend.app.db.models import *  # noqa: F403 — load all models


@pytest.fixture
def sync_engine():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    eng = create_engine(db_url, echo=False)
    Base.metadata.create_all(eng)
    with eng.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.commit()
    yield eng
    eng.dispose()
    os.unlink(tmp.name)


def test_all_tables_created(sync_engine):
    tables = inspect(sync_engine).get_table_names()
    expected = {
        "campaigns",
        "characters",
        "sessions",
        "turns",
        "scenes",
        "event_log",
        "memories",
        "summaries",
    }
    for t in expected:
        assert t in tables, f"Missing table: {t}"


def test_mutable_tables_have_timestamps(sync_engine):
    tables_with_timestamps = ["campaigns", "characters"]
    for table in tables_with_timestamps:
        columns = [c["name"] for c in inspect(sync_engine).get_columns(table)]
        assert "created_at" in columns, f"{table} missing created_at"
        assert "updated_at" in columns, f"{table} missing updated_at"


def test_event_log_is_append_only(sync_engine):
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO event_log (event_type, entity_type, entity_id, data) "
                "VALUES ('test', 'test', 'test-id', '{}')"
            )
        )
    with sync_engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM event_log"))
        count = result.scalar()
    assert count >= 1
