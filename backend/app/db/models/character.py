import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Character(Base):
    __tablename__ = "characters"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    player_name = Column(String(100), default="")
    character_name = Column(String(100), nullable=False)
    race = Column(String(50), default="")
    class_name = Column("class", String(50), default="")
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)
    hp_current = Column(Integer, default=10)
    hp_max = Column(Integer, default=10)
    strength = Column(Integer, default=10)
    dexterity = Column(Integer, default=10)
    constitution = Column(Integer, default=10)
    intelligence = Column(Integer, default=10)
    wisdom = Column(Integer, default=10)
    charisma = Column(Integer, default=10)
    armor_class = Column(Integer, default=10)
    initiative = Column(Integer, default=0)
    speed = Column(Integer, default=30)
    backstory = Column(Text, default="")
    created_at = Column(String(32), default=lambda: datetime.now(UTC).isoformat())
    updated_at = Column(
        String(32),
        default=lambda: datetime.now(UTC).isoformat(),
        onupdate=lambda: datetime.now(UTC).isoformat(),
    )

    campaign = relationship("Campaign", back_populates="characters")
