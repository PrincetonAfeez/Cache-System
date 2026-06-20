""" Test stats """

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cachelab import Cache


def test_stats_snapshot_is_immutable() -> None:
    cache = Cache(capacity=2)
    snapshot = cache.stats()
    with pytest.raises(FrozenInstanceError):
        snapshot.hits = 99  # type: ignore[misc]
