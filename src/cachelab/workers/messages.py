""" Messages utilities for CacheLab """

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Hashable


@dataclass(frozen=True, slots=True)
class ExpireShard:
    shard_index: int


@dataclass(frozen=True, slots=True)
class FlushWriteBack:
    shard_index: int
    key: Hashable
    value: Any
    version: int
    operation: str
    retries_left: int
    attempt: int = 0


@dataclass(frozen=True, slots=True)
class PreloadKey:
    shard_index: int
    key: Hashable
    loader: Callable[[], Any]
    ttl: float | None = None
    ttl_supplied: bool = False


@dataclass(frozen=True, slots=True)
class SnapshotStats:
    request_id: str


@dataclass(frozen=True, slots=True)
class StopWorker:
    reason: str = "shutdown"


Job = ExpireShard | FlushWriteBack | PreloadKey | SnapshotStats | StopWorker
