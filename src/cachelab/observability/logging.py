""" Logging utilities for CacheLab """

from __future__ import annotations

import logging
from typing import Any


def get_logger() -> logging.Logger:
    return logging.getLogger("cachelab")


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    # log_event runs on every hit/miss/put under the shard lock; skip the field
    # formatting entirely when INFO is disabled (the default) so observability
    # adds no measurable cost on the hot path.
    if not logger.isEnabledFor(logging.INFO):
        return
    parts = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
    logger.info("cachelab_event %s %s", event, parts)
