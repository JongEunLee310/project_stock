import json
import logging
from contextvars import ContextVar, Token
from typing import Any

from app.core.config import Settings

REQUEST_ID_HEADER = "X-Request-ID"
DEFAULT_REQUEST_ID = "-"

_request_id: ContextVar[str] = ContextVar("request_id", default=DEFAULT_REQUEST_ID)
_log_record_factory_configured = False
_HANDLER_MARKER = "_project_stock_logging_handler"

SENSITIVE_KEY_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "credential",
)
MASKED_VALUE = "***"


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: MASKED_VALUE if _is_sensitive_key(str(key)) else mask_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_sensitive(item) for item in value)
    return value


def setup_logging(settings: Settings) -> None:
    _configure_log_record_factory()

    handler = logging.StreamHandler()
    setattr(handler, _HANDLER_MARKER, True)
    handler.addFilter(SensitiveDataFilter())
    if settings.APP_ENV == "prod":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] "
                "request_id=%(request_id)s %(message)s"
            )
        )

    root_logger = logging.getLogger()
    root_logger.handlers = [
        existing_handler
        for existing_handler in root_logger.handlers
        if not getattr(existing_handler, _HANDLER_MARKER, False)
    ]
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def _configure_log_record_factory() -> None:
    global _log_record_factory_configured
    if _log_record_factory_configured:
        return

    previous_factory = logging.getLogRecordFactory()

    def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        record.request_id = get_request_id()
        return record

    logging.setLogRecordFactory(record_factory)
    _log_record_factory_configured = True


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive(record.msg)
        if record.args:
            record.args = mask_sensitive(record.args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", DEFAULT_REQUEST_ID),
        }
        for key in (
            "method",
            "path",
            "status_code",
            "latency_ms",
            "error_code",
            "detail",
            "provider",
            "operation",
        ):
            if hasattr(record, key):
                payload[key] = mask_sensitive(getattr(record, key))
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
