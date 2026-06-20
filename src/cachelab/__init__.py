""" CacheLab """

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from cachelab.core.cache import Cache
from cachelab.core.clock import FakeClock, MonotonicClock
from cachelab.core.config import CacheConfig
from cachelab.core.entry import CacheEntry, EntrySnapshot
from cachelab.core.exceptions import (
    CacheLabError,
    ConfigurationError,
    QueueBackpressureError,
    ShutdownFlushError,
    UnsupportedWriteModeError,
    ValidationError,
)
from cachelab.core.stats import CacheStatsSnapshot

try:
    __version__ = _pkg_version("cachelab")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.1.0"

__all__ = [
    "Cache",
    "CacheConfig",
    "CacheEntry",
    "CacheLabError",
    "CacheStatsSnapshot",
    "ConfigurationError",
    "EntrySnapshot",
    "FakeClock",
    "MonotonicClock",
    "QueueBackpressureError",
    "ShutdownFlushError",
    "UnsupportedWriteModeError",
    "ValidationError",
    "__version__",
]
