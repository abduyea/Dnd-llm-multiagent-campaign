import os
import tempfile
import uuid

import pytest
from sqlalchemy import create_engine, text

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


def test_no_event_log_orphans(sync_engine):
    with sync_engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM event_log"))
        count = result.scalar()
    assert count == 0, "event_log should be empty after schema creation"


def test_cascade_delete_campaign(sync_engine):
    with sync_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        campaign_id = str(uuid.uuid4())
        conn.execute(
            text("INSERT INTO campaigns (id, name) VALUES (:id, 'test')"),
            {"id": campaign_id},
        )
        conn.execute(
            text(
                "INSERT INTO characters (id, campaign_id, character_name) "
                "VALUES (:cid, :camp_id, 'orphan-test')"
            ),
            {"cid": str(uuid.uuid4()), "camp_id": campaign_id},
        )
        conn.execute(
            text(
                "INSERT INTO sessions (id, campaign_id, name) "
                "VALUES (:sid, :camp_id, 'orphan-test')"
            ),
            {"sid": str(uuid.uuid4()), "camp_id": campaign_id},
        )

    with sync_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.execute(text("DELETE FROM campaigns WHERE id = :id"), {"id": campaign_id})

    with sync_engine.connect() as conn:
        chars = conn.execute(
            text("SELECT COUNT(*) FROM characters WHERE campaign_id = :id"),
            {"id": campaign_id},
        )
        assert chars.scalar() == 0, "Characters not cascade-deleted"

        sessions = conn.execute(
            text("SELECT COUNT(*) FROM sessions WHERE campaign_id = :id"),
            {"id": campaign_id},
        )
        assert sessions.scalar() == 0, "Sessions not cascade-deleted"
