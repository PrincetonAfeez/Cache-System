""" FIFO policy utilities for CacheLab """

from __future__ import annotations

from collections import OrderedDict
from typing import Hashable


class FIFOPolicy:
    name = "fifo"

    def __init__(self) -> None:
        self._order: OrderedDict[Hashable, None] = OrderedDict()

    def on_get(self, key: Hashable) -> None:
        return

    def on_put(self, key: Hashable) -> None:
        if key not in self._order:
            self._order[key] = None

    def on_delete(self, key: Hashable) -> None:
        self._order.pop(key, None)

    def evict_candidate(self) -> Hashable | None:
        return next(iter(self._order), None)

    def clear(self) -> None:
        self._order.clear()

    def metadata_size(self) -> int:
        return len(self._order)

    def __len__(self) -> int:
        return len(self._order)
