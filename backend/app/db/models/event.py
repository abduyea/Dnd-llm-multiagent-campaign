"""
M11: the per-session ordered event store — the engine's save file.

This is distinct from the legacy ``event_log`` table (which is an audit log).
Here, the rows ARE the source of truth: "resume a session" means replay these
rows in ``seq`` order through the engine projection (architecture invariant
11). One row per engine event; ``event_json`` is the full serialized engine
``Event`` envelope (seq + cause + payload + timestamp).
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text

from backend.app.db.base import Base


class SessionEvent(Base):
    """One engine event, persisted in seq order per session."""

    __tablename__ = "session_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    seq = Column(Integer, nullable=False)
    kind = Column(String(40), nullable=False)  # the engine payload .type
    event_json = Column(Text, nullable=False)  # full Event.model_dump_json()
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())

    __table_args__ = (
        # Ordered + unique per session: the total order (engine invariant 4).
        Index("ix_session_events_session_seq", "session_id", "seq", unique=True),
    )
