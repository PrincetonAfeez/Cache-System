""" Base storage utilities for CacheLab """

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Hashable, Iterable

from cachelab.core.entry import CacheEntry


class StorageBackend(ABC):
    @abstractmethod
    def get_entry(self, key: Hashable) -> CacheEntry | None:
        ...

    @abstractmethod
    def put_entry(self, entry: CacheEntry) -> None:
        ...

    @abstractmethod
    def delete_entry(self, key: Hashable) -> bool:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...

    @abstractmethod
    def contains(self, key: Hashable) -> bool:
        ...

    @abstractmethod
    def size(self) -> int:
        ...

    @abstractmethod
    def keys(self) -> Iterable[Hashable]:
        ...

    @abstractmethod
    def entries(self) -> Iterable[CacheEntry]:
        ...
