import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Memory(Base):
    """Structured story facts extracted by the Memory Agent. Authoritative store."""

    __tablename__ = "memories"

    # The memory layer fetches per-session facts ordered by importance every turn,
    # so index (session_id, importance) to serve both the filter and the sort.
    __table_args__ = (Index("ix_memories_session_importance", "session_id", "importance"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id = Column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    fact_text = Column(Text, nullable=False)
    fact_type = Column(String(50), default="event")
    importance = Column(Integer, default=1)
    extracted_by = Column(String(50), default="memory_agent")
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())

    session = relationship("Session", back_populates="memories")


class Summary(Base):
    """Compressed session summaries, written on scene-end."""

    __tablename__ = "summaries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scene_id = Column(String(36), ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    summary_text = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())

    session = relationship("Session", back_populates="summaries")
