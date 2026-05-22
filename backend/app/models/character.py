from pydantic import BaseModel, Field


class CharacterCreate(BaseModel):
    player_name: str = ""
    character_name: str = Field(..., max_length=100)
    race: str = ""
    class_name: str = ""
    level: int = Field(default=1, ge=1, le=20)
    hp_max: int | None = Field(default=None, ge=1, le=999)
    strength: int = Field(default=10, ge=1, le=30)
    dexterity: int = Field(default=10, ge=1, le=30)
    constitution: int = Field(default=10, ge=1, le=30)
    intelligence: int = Field(default=10, ge=1, le=30)
    wisdom: int = Field(default=10, ge=1, le=30)
    charisma: int = Field(default=10, ge=1, le=30)
    armor_class: int = Field(default=10, ge=1)
    initiative: int = 0
    speed: int = 30
    backstory: str = ""


class CharacterResponse(BaseModel):
    id: str
    campaign_id: str
    player_name: str
    character_name: str
    race: str
    class_name: str
    level: int
    experience: int = 0
    hp_current: int
    hp_max: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    armor_class: int
    initiative: int
    speed: int
    backstory: str
    created_at: str
    updated_at: str


class CharacterUpdate(BaseModel):
    player_name: str | None = None
    character_name: str | None = None
    race: str | None = None
    class_name: str | None = None
    level: int | None = Field(default=None, ge=1, le=20)
    hp_current: int | None = Field(default=None, ge=1, le=999)
    hp_max: int | None = Field(default=None, ge=1, le=999)
    strength: int | None = Field(default=None, ge=1, le=30)
    dexterity: int | None = Field(default=None, ge=1, le=30)
    constitution: int | None = Field(default=None, ge=1, le=30)
    intelligence: int | None = Field(default=None, ge=1, le=30)
    wisdom: int | None = Field(default=None, ge=1, le=30)
    charisma: int | None = Field(default=None, ge=1, le=30)
    armor_class: int | None = Field(default=None, ge=1)
    initiative: int | None = None
    speed: int | None = None
    backstory: str | None = None
