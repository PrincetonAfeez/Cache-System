""" Single-flight utilities for CacheLab """

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Flight:
    event: threading.Event
    result: Any = None
    exception: BaseException | None = None
