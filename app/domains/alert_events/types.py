from enum import Enum


class AlertDeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class AlertEventStatus(str, Enum):
    UNREAD = "UNREAD"
    READ = "READ"
