import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), default="")
    status = Column(String(20), default="active")
    started_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())
    ended_at = Column(String(32), nullable=True)
    turn_count = Column(Integer, default=0)

    campaign = relationship("Campaign", back_populates="sessions")
    turns = relationship("Turn", back_populates="session", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="session", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="session", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="session", cascade="all, delete-orphan")


class Turn(Base):
    __tablename__ = "turns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(
        String(36), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    turn_number = Column(Integer, nullable=False)
    action_type = Column(String(50), default="")
    action_text = Column(Text, default="")
    dice_results = Column(Text, default="{}")
    attack_result = Column(Text, nullable=True)
    narration = Column(Text, default="")
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())

    session = relationship("Session", back_populates="turns")


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    scene_number = Column(Integer, nullable=False)
    title = Column(String(200), default="")
    description = Column(Text, default="")
    status = Column(String(20), default="active")
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())

    session = relationship("Session", back_populates="scenes")
