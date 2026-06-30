from pydantic import BaseModel


class BriefingResult(BaseModel):
    headline: str
    body: str
    risk_headline: str | None = None
    risk_checks: list[str]
