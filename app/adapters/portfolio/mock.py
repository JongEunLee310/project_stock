from decimal import Decimal

from app.adapters.portfolio.base import HoldingResult, PortfolioProvider


class MockPortfolioProvider(PortfolioProvider):
    def fetch_holdings(self, account_ref: str) -> list[HoldingResult]:
        return [
            HoldingResult(
                account_ref=account_ref,
                symbol="AAPL",
                quantity=Decimal("10"),
                average_cost=Decimal("150.00"),
                market_value=Decimal("1956.40"),
                currency="USD",
                payload={"account_ref": account_ref, "index": 1},
            ),
            HoldingResult(
                account_ref=account_ref,
                symbol="TSLA",
                quantity=Decimal("4"),
                average_cost=Decimal("210.00"),
                market_value=Decimal("729.24"),
                currency="USD",
                payload={"account_ref": account_ref, "index": 2},
            ),
        ]
