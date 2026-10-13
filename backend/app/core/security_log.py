"""CERT-In Directions 2022 security event log (Sprint 6).

Authentication and account events are appended as JSON lines to
`<SECURITY_LOG_DIR>/security.jsonl`, rotated at UTC midnight and kept for
`SECURITY_LOG_RETENTION_DAYS` (180) days. The directory lives on the
India-hosted VM; nothing here ever ships to a logging SaaS.

What goes in: event name, UTC timestamp, request id, user id, client IP, and a
few non-sensitive fields. What never goes in: passwords, tokens, query text, or
raw email addresses (failed logins carry a short hash so repeated attempts
against one account can be correlated without storing the address) --
CLAUDE.md's rule against writing user query text to a local file applies here
too.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from starlette.requests import Request

from app.core.compliance import SECURITY_LOG_RETENTION_DAYS
from app.core.logging import get_logger

LOG_FILENAME = "security.jsonl"

_file_logger = logging.getLogger("jurisai.security")
_file_logger.propagate = False
_file_logger.setLevel(logging.INFO)
_stdout_logger = get_logger("security")


def configure_security_log(log_dir: str) -> None:
    """(Re)attach the rotating file sink. Safe to call more than once; an
    empty `log_dir` leaves only the stdout sink (dev and tests)."""
    for handler in list(_file_logger.handlers):
        handler.close()
        _file_logger.removeHandler(handler)
    if not log_dir:
        return
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        directory / LOG_FILENAME,
        when="midnight",
        utc=True,
        backupCount=SECURITY_LOG_RETENTION_DAYS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    _file_logger.addHandler(handler)


def email_fingerprint(email: str) -> str:
    """Stable short hash so failed logins against one account correlate
    without the address itself being written to disk."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def audit(
    event: str,
    *,
    request: Request | None = None,
    user_id: str | None = None,
    **fields: Any,
) -> None:
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "request_id": structlog.contextvars.get_contextvars().get("request_id"),
        "user_id": user_id,
        "ip": request.client.host if request is not None and request.client else None,
        **fields,
    }
    _file_logger.info(json.dumps(record, default=str, sort_keys=True))
    _stdout_logger.info(event, **{k: v for k, v in record.items() if k != "event"})
