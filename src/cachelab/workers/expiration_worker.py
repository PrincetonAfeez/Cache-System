""" Expiration worker utilities for CacheLab """

from __future__ import annotations

from typing import Hashable, Iterable

from cachelab.core.entry import CacheEntry
from cachelab.workers.messages import ExpireShard

__all__ = ["ExpireShard", "expired_keys"]


def expired_keys(entries: Iterable[CacheEntry], now: float) -> list[Hashable]:
    """Return the keys of every entry that has expired at ``now``.

    Collecting keys first (rather than mutating while iterating) lets the caller
    remove them under its shard lock without invalidating the backend iterator.
    """
    return [entry.key for entry in entries if entry.is_expired(now)]
