from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from sqlalchemy.orm import Session

from app.domains.raw_prices.model import RawPrice
from app.domains.raw_prices.repository import RawPriceRepository
from app.domains.raw_prices.schema import RawPriceCreate


class RawPriceService:
    def __init__(self, db: Session) -> None:
        self.repo = RawPriceRepository(db)

    def save_raw(
        self,
        symbol: str,
        market: str,
        payload: dict[str, Any],
        interval: str = "1d",
        source: str = "yfinance",
    ) -> RawPrice | None:
        payload_hash = hash_payload(payload)
        if self.repo.exists_by_hash(payload_hash):
            return None
        return self.repo.save(
            RawPriceCreate(
                symbol=symbol.upper(),
                market=market.upper(),
                interval=interval,
                source=source,
                payload=payload,
                payload_hash=payload_hash,
                fetched_at=datetime.now(timezone.utc),
            )
        )


def hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
