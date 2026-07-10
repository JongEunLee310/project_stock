from enum import Enum


class SignalType(str, Enum):
    WATCH = "WATCH"
    RISK_ALERT = "RISK_ALERT"
    THESIS_BROKEN = "THESIS_BROKEN"
    BUY_CANDIDATE = "BUY_CANDIDATE"
    SELL_REVIEW = "SELL_REVIEW"
    OVERHEATED = "OVERHEATED"


class SignalCategory(str, Enum):
    WATCH = "WATCH"
    RISK = "RISK"
    BUY = "BUY"
    RESEARCH = "RESEARCH"


SIGNAL_TYPE_CATEGORY: dict[SignalType, SignalCategory] = {
    SignalType.WATCH: SignalCategory.WATCH,
    SignalType.RISK_ALERT: SignalCategory.RISK,
    SignalType.THESIS_BROKEN: SignalCategory.RISK,
    SignalType.BUY_CANDIDATE: SignalCategory.BUY,
    SignalType.SELL_REVIEW: SignalCategory.RESEARCH,
    SignalType.OVERHEATED: SignalCategory.RESEARCH,
}

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


def signal_priority_rank(signal_type: str | None) -> int | None:
    if signal_type is None:
        return None
    rank_by_type = {
        status_type.value: rank
        for rank, status_type in enumerate(WATCHLIST_STATUS_PRIORITY)
    }
    return rank_by_type.get(signal_type, len(rank_by_type))


def signal_category_for_type(signal_type: str | None) -> SignalCategory | None:
    if signal_type is None:
        return None
    try:
        typed_signal = SignalType(signal_type)
    except ValueError:
        return None
    return SIGNAL_TYPE_CATEGORY.get(typed_signal)
