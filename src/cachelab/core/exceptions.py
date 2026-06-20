""" Exception utilities for CacheLab """

from __future__ import annotations


class CacheLabError(Exception):
    """Base class for cachelab errors."""


class ConfigurationError(CacheLabError):
    """Raised when a cache configuration is invalid."""


class QueueBackpressureError(CacheLabError):
    """Raised when a critical worker job cannot be enqueued safely."""


class ShutdownFlushError(CacheLabError):
    """Raised when close(flush=True) cannot persist dirty write-back entries."""


class UnsupportedWriteModeError(CacheLabError):
    """Raised when an unknown write mode is requested."""


class ValidationError(CacheLabError):
    """Raised when caller-supplied arguments are invalid."""
