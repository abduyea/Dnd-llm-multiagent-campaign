from datetime import UTC, datetime

from sqlalchemy import Column, Integer, String, Text

from backend.app.db.base import Base


class EventLog(Base):
    """Append-only event log for auditing and replay."""

    __tablename__ = "event_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False, index=True)
    data = Column(Text, default="{}")
    agent_id = Column(String(50), default="system")
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())
