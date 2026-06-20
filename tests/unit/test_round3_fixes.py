""" Test round3 fixes """

from __future__ import annotations

from pathlib import Path

import pytest

from cachelab import Cache, CacheConfig
from cachelab.core.exceptions import ShutdownFlushError
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode


def test_close_flush_true_succeeds_when_workers_never_started() -> None:
    backend = SlowDictBackend()
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=2,
        source_backend=backend,
    )
    cache.put("a", 1)
    cache.close(flush=True)
    assert backend.get_value("a") == 1
    assert cache.stats().queue_depth == 0


def test_preload_queue_settled_after_close_without_start() -> None:
    cache = Cache(capacity=4, worker_count=1)
    assert cache.preload("k", lambda: "v")
    cache.close(flush=False)
    assert cache.stats().queue_depth == 0


def test_shutdown_flush_error_includes_dirty_count() -> None:
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
    with pytest.raises(ShutdownFlushError, match=r"1 still dirty"):
        cache.close(flush=True)


def test_state_reload_warns_on_dropped_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import argparse

    from cachelab.cli.commands.basic import _load_cache_state, _save_cache_state

    state = tmp_path / "state.json"
    cache = Cache(capacity=10, shard_count=1)
    for index in range(8):
        cache.put(f"k{index}", index)
    _save_cache_state(state, cache)
    args = argparse.Namespace(
        config=None, capacity=3, policy="lru", shards=1, default_ttl=None
    )
    restored = _load_cache_state(state, args)
    assert restored.size() == 3
    err = capsys.readouterr().err
    assert "dropped during reload" in err


def test_preload_warns_when_cache_not_started(caplog: pytest.LogCaptureFixture) -> None:
    cache = Cache(capacity=4, worker_count=1)
    cache.preload("k", lambda: "v")
    assert any("cache_not_started" in record.message for record in caplog.records)


def test_default_ttl_mismatch_warned_on_reload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import argparse

    from cachelab.cli.commands.basic import _load_cache_state, _save_cache_state

    state = tmp_path / "state.json"
    cache = Cache(capacity=4, default_ttl=60)
    cache.put("k", "v")
    _save_cache_state(state, cache)
    args = argparse.Namespace(
        config=None, capacity=4, policy="lru", shards=1, default_ttl=30
    )
    _load_cache_state(state, args)
    assert "default_ttl" in capsys.readouterr().err
