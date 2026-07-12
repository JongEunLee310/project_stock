SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Communication Services": "XLC",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
}


def resolve_sector_etf(sector: str | None) -> tuple[str, str, str]:
    symbol = SECTOR_ETFS.get(sector) if sector is not None else None
    if symbol is None:
        return "SPY", "NYSE", "S&P 500"
    return symbol, "NYSE", symbol
