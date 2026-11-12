"""JSON log lines on stdout (docs/runtime-contract.md). Never log amounts or names."""
import json
import logging
import os
import sys
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id: ContextVar[str | None] = ContextVar("run_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "service": os.environ.get("SERVICE_NAME", "api"), "event": record.getMessage(),
                "logger": record.name}
        for key, var in (("request_id", request_id), ("run_id", run_id)):
            if var.get():
                line[key] = var.get()
        line.update(getattr(record, "fields", {}))
        if record.exc_info:
            # Frames and type only: exception messages can carry invoice data (DESIGN.md 12)
            etype, _, tb = record.exc_info
            line["error_type"] = etype.__name__ if etype else None
            line["error"] = "".join(traceback.format_tb(tb))
        return json.dumps(line, default=str)


def setup() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    for name in ("uvicorn", "uvicorn.error"):  # send uvicorn's own lines through our JSON
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True  # we log requests ourselves


def log(event: str, level: int = logging.INFO, exc_info: bool = False, **fields) -> None:
    logging.getLogger("gstr2b").log(level, event, exc_info=exc_info, extra={"fields": fields})
