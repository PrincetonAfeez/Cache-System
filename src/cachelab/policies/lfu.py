""" LFU policy utilities for CacheLab """

from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Hashable


class LFUPolicy:
    """O(1) LFU with recency tie-breaking inside frequency buckets."""

    name = "lfu"

    def __init__(self) -> None:
        self._key_to_freq: dict[Hashable, int] = {}
        self._freq_to_keys: dict[int, OrderedDict[Hashable, None]] = defaultdict(OrderedDict)
        self._min_freq = 0

    def on_get(self, key: Hashable) -> None:
        if key in self._key_to_freq:
            self._bump(key)

    def on_put(self, key: Hashable) -> None:
        if key in self._key_to_freq:
            self._bump(key)
            return
        self._key_to_freq[key] = 1
        self._freq_to_keys[1][key] = None
        self._min_freq = 1

    def on_delete(self, key: Hashable) -> None:
        freq = self._key_to_freq.pop(key, None)
        if freq is None:
            return
        bucket = self._freq_to_keys[freq]
        bucket.pop(key, None)
        if not bucket:
            del self._freq_to_keys[freq]
            if self._min_freq == freq:
                self._min_freq = min(self._freq_to_keys, default=0)

    def evict_candidate(self) -> Hashable | None:
        if self._min_freq == 0:
            return None
        bucket = self._freq_to_keys.get(self._min_freq)
        if not bucket:
            return None
        return next(iter(bucket), None)

    def clear(self) -> None:
        self._key_to_freq.clear()
        self._freq_to_keys.clear()
        self._min_freq = 0

    def metadata_size(self) -> int:
        return len(self._key_to_freq) + sum(len(keys) for keys in self._freq_to_keys.values())

    def __len__(self) -> int:
        return len(self._key_to_freq)

    def _bump(self, key: Hashable) -> None:
        old_freq = self._key_to_freq[key]
        old_bucket = self._freq_to_keys[old_freq]
        old_bucket.pop(key, None)
        if not old_bucket:
            del self._freq_to_keys[old_freq]
            if self._min_freq == old_freq:
                self._min_freq = old_freq + 1
        new_freq = old_freq + 1
        self._key_to_freq[key] = new_freq
        self._freq_to_keys[new_freq][key] = None
