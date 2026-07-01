from pydantic import BaseModel


class BriefingResult(BaseModel):
    headline: str
    body: str
    risk_headline: str | None = None
    risk_checks: list[str]


class ObservationItem(BaseModel):
    symbol: str
    note: str


class ObservationsResult(BaseModel):
    summary: str
    items: list[ObservationItem]
