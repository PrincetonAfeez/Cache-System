""" Entry utilities for CacheLab """

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable


@dataclass(slots=True)
class CacheEntry:
    key: Hashable
    value: Any
    created_at: float
    last_accessed_at: float
    hit_count: int
    expires_at: float | None
    ttl: float | None
    version: int
    dirty: bool = False

    def is_expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def touch(self, now: float) -> None:
        self.last_accessed_at = now
        self.hit_count += 1

    def snapshot(self, now: float) -> "EntrySnapshot":
        remaining = None if self.expires_at is None else max(0.0, self.expires_at - now)
        return EntrySnapshot(
            key=self.key,
            value=self.value,
            created_at=self.created_at,
            last_accessed_at=self.last_accessed_at,
            hit_count=self.hit_count,
            expires_at=self.expires_at,
            ttl=self.ttl,
            ttl_remaining=remaining,
            version=self.version,
            dirty=self.dirty,
        )


@dataclass(frozen=True, slots=True)
class EntrySnapshot:
    key: Hashable
    value: Any
    created_at: float
    last_accessed_at: float
    hit_count: int
    expires_at: float | None
    ttl: float | None
    ttl_remaining: float | None
    version: int
    dirty: bool
