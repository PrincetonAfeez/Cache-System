""" Test round2 fixes """

from __future__ import annotations

from pathlib import Path

import pytest

from cachelab import Cache, CacheConfig
from cachelab.core.exceptions import ConfigurationError, ShutdownFlushError
from cachelab.core.lifecycle import LifecycleState
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode


def test_failed_shutdown_flush_clears_pending_flushes() -> None:
    backend = SlowDictBackend()
    backend.fail_next(100)
    cache = Cache(
        config=CacheConfig(
            capacity=4,
            write_mode=WriteMode.WRITE_BACK.value,
            worker_count=0,
            write_back_retry_count=0,
        ),
        source_backend=backend,
    )
    cache.put("a", 1)
    with pytest.raises(ShutdownFlushError):
        cache.close(flush=True)
    assert cache._shards[0].pending_flushes == {}
    entry = cache._shards[0].backend.get_entry("a")
    assert entry is not None
    assert entry.dirty is True


def test_scheduler_tick_blocked_after_close() -> None:
    cache = Cache(capacity=4, worker_count=1)
    cache.start()
    cache.close(flush=False)
    with pytest.raises(RuntimeError, match="closed cache"):
        cache.scheduler_tick()


def test_stats_allowed_after_close() -> None:
    cache = Cache(capacity=4, worker_count=1)
    cache.start()
    cache.put("a", 1)
    cache.close(flush=False)
    assert cache.stats().size == 1


def test_close_blocks_concurrent_put_during_shutdown() -> None:
    import threading

    cache = Cache(capacity=8, worker_count=1)
    cache.start()
    blocked: list[str] = []

    def closer() -> None:
        cache.close(flush=False)

    def writer() -> None:
        for index in range(100):
            try:
                cache.put(f"k{index}", index)
            except RuntimeError:
                blocked.append("closed")
                return

    t1 = threading.Thread(target=closer)
    t2 = threading.Thread(target=writer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert cache._state == LifecycleState.CLOSED
    assert blocked


def test_write_back_warns_when_workers_configured_but_not_started(caplog: pytest.LogCaptureFixture) -> None:
    cache = Cache(capacity=4, write_mode=WriteMode.WRITE_BACK.value, worker_count=2)
    cache.put("a", 1)
    assert any("cache_not_started" in record.message for record in caplog.records)


def test_make_policy_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        from cachelab.policies.base import make_policy

        make_policy("bogus")


def test_state_file_persists_config_and_hit_count(tmp_path: Path) -> None:
    import argparse

    from cachelab.cli.commands.basic import _load_cache_state, _save_cache_state

    state = tmp_path / "state.json"
    cache = Cache(capacity=8, policy="fifo", shard_count=2)
    cache.put("k", "v")
    cache.get("k")
    cache.get("k")
    inspected = cache.inspect("k")
    assert inspected is not None
    assert inspected.hit_count == 2
    _save_cache_state(state, cache)
    args = argparse.Namespace(config=None, capacity=8, policy="fifo", shards=2)
    restored = _load_cache_state(state, args)
    snap = restored.inspect("k")
    assert snap is not None
    assert snap.hit_count == 2
    saved = state.read_text(encoding="utf-8")
    assert '"config"' in saved
    assert '"fifo"' in saved


def test_dump_limit_is_not_shard_biased() -> None:
    cache = Cache(capacity=10, shard_count=4)
    for index in range(8):
        cache.put(f"k{index}", index)
    keys = {snap.key for snap in cache.dump(limit=8)}
    assert len(keys) == 8


def test_cli_get_single_hit_count(tmp_path: Path) -> None:
    import argparse

    from cachelab.cli.commands.basic import _load_cache_state
    from cachelab.cli.main import main

    state = tmp_path / "state.json"
    assert main(["--state", str(state), "put", "k", "v"]) == 0
    assert main(["--state", str(state), "get", "k"]) == 0
    args = argparse.Namespace(config=None, capacity=128, policy="lru", shards=1)
    cache = _load_cache_state(state, args)
    cache.get("k")
    assert cache.stats().hits == 1
