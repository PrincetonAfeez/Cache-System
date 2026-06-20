""" Lifecycle utilities for CacheLab """

from __future__ import annotations

from enum import Enum


class LifecycleState(str, Enum):
    CREATED = "created"
    STARTED = "started"
    CLOSING = "closing"
    CLOSED = "closed"
