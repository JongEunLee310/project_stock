from enum import Enum


class SignalType(str, Enum):
    WATCH = "WATCH"
    RISK_ALERT = "RISK_ALERT"
    THESIS_BROKEN = "THESIS_BROKEN"
    BUY_CANDIDATE = "BUY_CANDIDATE"
    SELL_REVIEW = "SELL_REVIEW"
    OVERHEATED = "OVERHEATED"


WATCHLIST_STATUS_NORMAL = "NORMAL"
WATCHLIST_STATUS_PRIORITY: tuple[SignalType, ...] = (
    SignalType.RISK_ALERT,
    SignalType.THESIS_BROKEN,
    SignalType.SELL_REVIEW,
    SignalType.OVERHEATED,
    SignalType.BUY_CANDIDATE,
    SignalType.WATCH,
)


def resolve_watchlist_status(active_types: set[str]) -> str:
    for signal_type in WATCHLIST_STATUS_PRIORITY:
        if signal_type.value in active_types:
            return signal_type.value
    return WATCHLIST_STATUS_NORMAL
