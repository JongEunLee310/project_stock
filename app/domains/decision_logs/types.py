from enum import Enum


class DecisionType(str, Enum):
    WATCH = "WATCH"
    BUY_CONSIDER = "BUY_CONSIDER"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL_CONSIDER = "SELL_CONSIDER"
    SELL = "SELL"
    SKIP = "SKIP"
    REBALANCE = "REBALANCE"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"


class DecisionStatus(str, Enum):
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    CLOSED = "CLOSED"


class CreatedBy(str, Enum):
    USER = "USER"
    AI = "AI"
    SYSTEM = "SYSTEM"
