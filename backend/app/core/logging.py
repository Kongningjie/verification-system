import json
import logging
from datetime import UTC, datetime


class JsonLogFormatter(logging.Formatter):
    """Emit the stable, redacted business-log envelope required by the frozen plan."""

    fields = (
        "request_id",
        "task_id",
        "stage",
        "check_item_id",
        "operation",
        "duration_ms",
        "error_code",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            **{field: getattr(record, field, None) for field in self.fields},
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_business_logging() -> None:
    logger = logging.getLogger("app")
    if any(getattr(handler, "business_json", False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler.business_json = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
