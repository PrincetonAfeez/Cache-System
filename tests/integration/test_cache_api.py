""" Test cache API """

from __future__ import annotations

import pytest

from cachelab import Cache
from cachelab.core.exceptions import ConfigurationError


def test_get_default_distinguishes_cached_none_from_miss() -> None:
    cache = Cache(capacity=4)
    cache.put("k", None)
    sentinel = object()
    assert cache.get("k", sentinel) is None  # a genuinely cached None
    assert cache.get("absent", sentinel) is sentinel  # a real miss
    assert cache.get("k") is None
    assert cache.get("absent") is None


def test_cache_backend_kwarg_is_validated() -> None:
    Cache(capacity=4, backend="memory")  # supported
    with pytest.raises(ConfigurationError):
        Cache(capacity=4, backend="redis")


def test_cache_api_update_delete_clear_inspect() -> None:
    cache = Cache(capacity=2, shard_count=1)
    cache.put("a", "one")
    cache.put("a", "two")
    assert cache.size() == 1
    inspected = cache.inspect("a")
    assert inspected is not None
    assert inspected.value == "two"
    assert inspected.version == 2
    assert cache.contains("a")
    assert cache.delete("a")
    assert cache.stats().deletes == 1
    assert not cache.contains("a")
    assert cache.delete("missing") is False
    assert cache.stats().deletes == 1
    cache.put("b", "two")
    cache.put("c", "three")
    cache.clear()
    assert cache.size() == 0
    assert cache.stats().deletes == 3


def test_context_manager_starts_and_closes_cleanly() -> None:
    with Cache(capacity=2, worker_count=1, scheduler_interval=10) as cache:
        assert cache.alive_threads()
    assert cache.alive_threads() == []
