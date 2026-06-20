""" Test audit fixes """

from __future__ import annotations

from pathlib import Path

import pytest

from cachelab import Cache, CacheConfig, ConfigurationError
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode


def test_delete_stat_counts_only_successful_removals() -> None:
    cache = Cache(capacity=4)
    assert cache.delete("missing") is False
    assert cache.stats().deletes == 0
    cache.put("a", 1)
    assert cache.delete("a") is True
    assert cache.stats().deletes == 1


def test_clear_increments_delete_stat_per_key() -> None:
    cache = Cache(capacity=4)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.clear()
    assert cache.stats().deletes == 2


def test_closed_cache_rejects_mutations() -> None:
    cache = Cache(capacity=4, worker_count=1)
    cache.start()
    cache.close(flush=False)
    with pytest.raises(RuntimeError, match="closed cache"):
        cache.put("k", "v")
    with pytest.raises(RuntimeError, match="closed cache"):
        cache.get("k")


def test_write_back_close_clears_pending_flushes_without_workers() -> None:
    backend = SlowDictBackend()
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=0,
        source_backend=backend,
    )
    cache.put("a", 1)
    cache.close()
    assert cache._shards[0].pending_flushes == {}
    assert backend.get_value("a") == 1


def test_cache_rejects_conflicting_config_and_kwargs() -> None:
    config = CacheConfig(capacity=4)
    with pytest.raises(ConfigurationError, match="do not also pass"):
        Cache(config=config, capacity=999)


def test_active_expiration_requires_positive_scheduler_interval() -> None:
    with pytest.raises(ConfigurationError, match="scheduler_interval"):
        CacheConfig(active_expiration=True, scheduler_interval=0)


def test_preload_uses_default_ttl_when_omitted() -> None:
    cache = Cache(capacity=8, default_ttl=60, worker_count=1, scheduler_interval=10)
    cache.start()
    assert cache.preload("k", lambda: "warm")
    assert cache.job_queue.join_until(1)
    inspected = cache.inspect("k")
    assert inspected is not None
    assert inspected.ttl == 60
    cache.close(flush=False)


def test_state_file_preserves_integer_keys(tmp_path: Path) -> None:
    import argparse

    from cachelab.cli.commands.basic import _load_cache_state, _save_cache_state

    state = tmp_path / "state.json"
    cache = Cache(capacity=8)
    cache.put(42, "int-key")
    _save_cache_state(state, cache)
    args = argparse.Namespace(config=None, capacity=8, policy="lru", shards=1)
    restored = _load_cache_state(state, args)
    assert restored.contains(42)
    assert not restored.contains("42")
