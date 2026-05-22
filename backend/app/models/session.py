from pydantic import BaseModel


class SessionCreate(BaseModel):
    name: str = ""
    campaign_id: str


class SessionResponse(BaseModel):
    id: str
    campaign_id: str
    name: str
    status: str
    started_at: str
    ended_at: str | None
    turn_count: int
    summary: str | None = None


class SessionEnd(BaseModel):
    status: str = "completed"
