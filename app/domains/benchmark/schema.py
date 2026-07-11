from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class BenchmarkRange(str, Enum):
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"


class BenchmarkSeriesKind(str, Enum):
    ASSET = "ASSET"
    INDEX = "INDEX"
    SECTOR_ETF = "SECTOR_ETF"


class BenchmarkPoint(BaseModel):
    date: date
    return_percent: Decimal


class BenchmarkSeries(BaseModel):
    kind: BenchmarkSeriesKind
    label: str
    points: list[BenchmarkPoint]


class BenchmarkComparisonResponse(BaseModel):
    asset_id: int
    range: BenchmarkRange
    series: list[BenchmarkSeries]
