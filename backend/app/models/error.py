from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str = ""
    violations: list[dict[str, str]] = Field(default_factory=list)
