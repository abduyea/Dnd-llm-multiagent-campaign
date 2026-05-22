import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    world_setting = Column(Text, default="")
    status = Column(String(20), default="active")
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())
    updated_at = Column(
        String(32),
        default=lambda: datetime.now(UTC).isoformat(),
        onupdate=lambda: datetime.now(UTC).isoformat(),
    )

    characters = relationship("Character", back_populates="campaign", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="campaign", cascade="all, delete-orphan")
