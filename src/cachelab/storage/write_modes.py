""" Write mode utilities for CacheLab """

from __future__ import annotations

from enum import Enum


class WriteMode(str, Enum):
    CACHE_ONLY = "cache-only"
    WRITE_THROUGH = "write-through"
    WRITE_BACK = "write-back"
