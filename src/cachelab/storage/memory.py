""" Memory storage utilities for CacheLab """

from __future__ import annotations

from typing import Hashable, Iterable

from cachelab.core.entry import CacheEntry
from cachelab.storage.base import StorageBackend


class InMemoryBackend(StorageBackend):
    def __init__(self) -> None:
        self._entries: dict[Hashable, CacheEntry] = {}

    def get_entry(self, key: Hashable) -> CacheEntry | None:
        return self._entries.get(key)

    def put_entry(self, entry: CacheEntry) -> None:
        self._entries[entry.key] = entry

    def delete_entry(self, key: Hashable) -> bool:
        return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        self._entries.clear()

    def contains(self, key: Hashable) -> bool:
        return key in self._entries

    def size(self) -> int:
        return len(self._entries)

    def keys(self) -> Iterable[Hashable]:
        return tuple(self._entries.keys())

    def entries(self) -> Iterable[CacheEntry]:
        return tuple(self._entries.values())
