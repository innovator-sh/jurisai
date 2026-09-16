import logging
import sys
from typing import cast

import structlog


def configure_logging(log_level: str) -> None:
    """JSON logs to stdout — container-native, no local log files.
    Never log raw query text at this level; that's a Sprint 4 redaction concern."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    # Legacy logged every third-party call at DEBUG (D047); keep our own logger
    # scoped and quiet the noisy ones regardless of our own level.
    for noisy in ("pymongo", "httpx", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
