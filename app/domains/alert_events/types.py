from enum import Enum


class AlertEventSource(str, Enum):
    RULE = "RULE"
    AGENT = "AGENT"


class AlertDeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AlertEventStatus(str, Enum):
    UNREAD = "UNREAD"
    READ = "READ"
