import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Only application-controlled messages; never serialize requests or exception strings.
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "event": record.getMessage(),
                "request_id": getattr(record, "request_id", None),
            }
        )


def configure_logging(level: str) -> None:
    logger = logging.getLogger("edumind")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
