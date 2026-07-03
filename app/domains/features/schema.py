from decimal import Decimal

from pydantic import BaseModel


class PriceFeatureSet(BaseModel):
    return_1d: Decimal | None
    return_5d: Decimal | None
    return_20d: Decimal | None
    volume_vs_20d_avg: Decimal | None
    drawdown_from_52w_high: Decimal | None

