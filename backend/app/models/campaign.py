from pydantic import BaseModel, Field


class CharacterExport(BaseModel):
    """Single-character slice of a campaign export bundle."""

    character_name: str
    player_name: str = ""
    race: str = ""
    class_name: str = ""
    level: int = 1
    experience: int = 0
    hp_current: int = 10
    hp_max: int = 10
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    armor_class: int = 10
    initiative: int = 0
    speed: int = 30
    backstory: str = ""


class CampaignMetaExport(BaseModel):
    """Campaign metadata slice of a campaign export bundle."""

    name: str
    description: str = ""
    world_setting: str = ""
    status: str = "active"


class CampaignBundle(BaseModel):
    """Portable campaign export/import bundle (version 1.0)."""

    version: str = "1.0"
    exported_at: str = ""
    campaign: CampaignMetaExport
    characters: list[CharacterExport] = Field(default_factory=list)


class CampaignCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str = ""
    world_setting: str = ""


class CampaignResponse(BaseModel):
    id: str
    name: str
    description: str
    world_setting: str
    status: str
    created_at: str
    updated_at: str
    character_count: int = 0
    session_count: int = 0


class CampaignListResponse(BaseModel):
    campaigns: list[CampaignResponse]
    total: int


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    world_setting: str | None = None
    status: str | None = None
