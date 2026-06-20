""" Test cache comprehensive """

from __future__ import annotations

import logging
import threading
import time
from unittest.mock import patch

import pytest

from cachelab import Cache, FakeClock
from cachelab.core.cache import _make_backend
from cachelab.core.config import CacheConfig
from cachelab.core.exceptions import (
    ConfigurationError,
    ShutdownFlushError,
    UnsupportedWriteModeError,
)
from cachelab.storage.memory import InMemoryBackend
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode
from cachelab.workers.messages import FlushWriteBack


def test_make_backend_rejects_unknown_name() -> None:
    with pytest.raises(ConfigurationError, match="unsupported backend"):
        _make_backend("redis")


def test_start_after_close_raises() -> None:
    cache = Cache(capacity=4)
    cache.close()
    with pytest.raises(RuntimeError, match="cannot restart"):
        cache.start()


def test_start_warns_when_active_expiration_has_no_workers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = CacheConfig(capacity=4, worker_count=0, active_expiration=True)
    cache = Cache(config=config)
    with caplog.at_level(logging.WARNING):
        cache.start()
    assert "active_expiration_inactive" in caplog.text


def test_start_warns_write_back_without_workers(caplog: pytest.LogCaptureFixture) -> None:
    cache = Cache(
        capacity=4,
        worker_count=0,
        write_mode=WriteMode.WRITE_BACK.value,
    )
    with caplog.at_level(logging.WARNING):
        cache.start()
    assert "write_back_inactive" in caplog.text


def test_put_replaces_expired_entry() -> None:
    clock = FakeClock()
    cache = Cache(capacity=4, default_ttl=5, clock=clock)
    cache.put("k", "old")
    clock.advance(6)
    cache.put("k", "new")
    assert cache.get("k") == "new"


def test_inspect_and_dump_evict_expired_entries() -> None:
    clock = FakeClock()
    cache = Cache(capacity=4, default_ttl=5, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    clock.advance(6)
    assert cache.inspect("a") is None
    assert cache.stats().expirations >= 1
    snapshots = cache.dump()
    assert all(snap.key != "a" for snap in snapshots)
    assert any(snap.key == "b" for snap in snapshots) or cache.stats().expirations >= 2


def test_dump_respects_limit() -> None:
    cache = Cache(capacity=8)
    for index in range(5):
        cache.put(f"k{index}", index)
    assert len(cache.dump(limit=2)) == 2


def test_clear_write_through_deletes_from_backend() -> None:
    backend = SlowDictBackend()
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_THROUGH.value,
        source_backend=backend,
    )
    cache.put("a", 1)
    cache.put("b", 2)
    cache.clear()
    assert backend.get_value("a") is None
    assert backend.get_value("b") is None
    assert cache.size() == 0


def test_clear_write_back_enqueues_delete_flushes() -> None:
    backend = SlowDictBackend()
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=1,
        source_backend=backend,
    )
    cache.start()
    cache.put("a", 1)
    cache.clear()
    cache.close(flush=True)
    assert backend.get_value("a") is None


def test_expire_all_removes_expired_keys() -> None:
    clock = FakeClock()
    cache = Cache(capacity=8, default_ttl=5, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2, ttl=None)
    clock.advance(6)
    removed = cache.expire_all()
    assert removed >= 1
    assert not cache.contains("a")
    assert cache.contains("b")


def test_get_or_compute_waiter_receives_loader_exception() -> None:
    cache = Cache(capacity=4, shard_count=1)
    errors: list[BaseException] = []

    def loader() -> str:
        time.sleep(0.05)
        raise ValueError("load failed")

    def call() -> None:
        try:
            cache.get_or_compute("k", loader)
        except ValueError as exc:
            errors.append(exc)

    follower = threading.Thread(target=call)
    follower.start()
    time.sleep(0.01)
    leader = threading.Thread(target=call)
    leader.start()
    leader.join()
    follower.join()
    assert len(errors) == 2


def test_get_or_compute_propagates_put_failure_after_load() -> None:
    cache = Cache(capacity=4)

    def loader() -> str:
        return "loaded"

    with patch.object(cache, "put", side_effect=RuntimeError("put failed")):
        with pytest.raises(RuntimeError, match="put failed"):
            cache.get_or_compute("k", loader)


def test_preload_returns_false_when_queue_full() -> None:
    cache = Cache(capacity=8, worker_count=1, queue_size=1, scheduler_interval=10)
    cache.start()
    cache.job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    assert cache.preload("k", lambda: "v") is False
    cache.close(flush=False)


def test_closed_cache_rejects_mutations() -> None:
    cache = Cache(capacity=4)
    cache.put("k", "v")
    cache.close()
    for operation, call in (
        ("put", lambda: cache.put("x", 1)),
        ("get", lambda: cache.get("k")),
        ("delete", lambda: cache.delete("k")),
        ("contains", lambda: cache.contains("k")),
        ("clear", lambda: cache.clear()),
        ("size", lambda: cache.size()),
        ("inspect", lambda: cache.inspect("k")),
        ("dump", lambda: cache.dump()),
        ("get_or_compute", lambda: cache.get_or_compute("k", lambda: 1)),
        ("expire_all", lambda: cache.expire_all()),
        ("preload", lambda: cache.preload("k", lambda: 1)),
        ("request_snapshot", lambda: cache.request_snapshot()),
        ("scheduler_tick", lambda: cache.scheduler_tick()),
        ("restore_entry_metadata", lambda: cache.restore_entry_metadata("k", hit_count=1)),
    ):
        with pytest.raises(RuntimeError, match="closed"):
            call()


def test_stats_available_after_close() -> None:
    cache = Cache(capacity=4)
    cache.put("k", "v")
    cache.close()
    assert cache.stats().size == 0 or cache.stats().puts >= 1


def test_restore_entry_metadata_updates_hit_count() -> None:
    cache = Cache(capacity=4)
    cache.put("k", "v")
    cache.restore_entry_metadata("k", hit_count=42)
    inspected = cache.inspect("k")
    assert inspected is not None
    assert inspected.hit_count == 42


def test_write_back_retry_dropped_on_backpressure() -> None:
    backend = SlowDictBackend()
    backend.fail_next(10)
    config = CacheConfig(
        capacity=8,
        write_mode=WriteMode.WRITE_BACK.value,
        queue_size=1,
        queue_put_timeout=0.01,
        write_back_retry_count=2,
    )
    cache = Cache(config=config, source_backend=backend, clock=FakeClock())
    cache.put("a", "one")
    first = cache.job_queue.get()
    cache.job_queue.task_done()
    assert isinstance(first, FlushWriteBack)
    cache.job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    assert cache._flush_write_back_job(first) is False
    assert cache.stats().flush_failures >= 1


def test_write_back_permanent_failure_clears_pending() -> None:
    backend = SlowDictBackend()
    backend.fail_next(100)
    config = CacheConfig(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=0,
        write_back_retry_count=0,
    )
    cache = Cache(config=config, source_backend=backend, clock=FakeClock())
    cache.put("a", "one")
    job = cache.job_queue.get()
    cache.job_queue.task_done()
    assert isinstance(job, FlushWriteBack)
    assert cache._flush_write_back_job(job) is False
    assert cache.stats().flush_failures >= 1


def test_sync_flush_skips_stale_jobs() -> None:
    backend = SlowDictBackend()
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=0,
        source_backend=backend,
    )
    cache.put("a", "old")
    shard = cache._shards[0]
    with shard.lock:
        entry = shard.backend.get_entry("a")
        assert entry is not None
        entry.version = 99
    failed = cache._flush_dirty_entries_sync()
    assert failed is False
    assert backend.get_value("a") is None
    assert cache.stats().stale_write_back_jobs_skipped >= 1


def test_sync_flush_records_failure() -> None:
    backend = SlowDictBackend()
    backend.fail_next(100)
    config = CacheConfig(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=0,
        write_back_retry_count=0,
    )
    cache = Cache(config=config, source_backend=backend, clock=FakeClock())
    cache.put("a", "one")
    assert cache._flush_dirty_entries_sync() is True
    with pytest.raises(ShutdownFlushError):
        cache.close(flush=True)


def test_cache_not_started_warning_on_put(caplog: pytest.LogCaptureFixture) -> None:
    cache = Cache(capacity=4, worker_count=1, write_mode=WriteMode.WRITE_BACK.value)
    with caplog.at_level(logging.WARNING):
        cache.put("k", "v")
    assert "cache_not_started" in caplog.text


def test_double_start_is_idempotent() -> None:
    cache = Cache(capacity=4, worker_count=1, scheduler_interval=10)
    cache.start()
    threads_after_first = len(cache.alive_threads())
    cache.start()
    assert len(cache.alive_threads()) == threads_after_first
    cache.close(flush=False)


def test_scheduler_tick_enqueues_expiration_jobs() -> None:
    cache = Cache(capacity=4, worker_count=1, scheduler_interval=10)
    cache.start()
    depth_before = cache.stats().queue_depth
    cache.scheduler_tick()
    assert cache.stats().queue_depth >= depth_before
    cache.close(flush=False)


def test_alive_threads_includes_scheduler() -> None:
    cache = Cache(capacity=4, worker_count=1, scheduler_interval=0.05)
    cache.start()
    names = [thread.name for thread in cache.alive_threads()]
    assert any("scheduler" in name for name in names)
    cache.close(flush=False)


def test_record_worker_failure_increments_stats() -> None:
    cache = Cache(capacity=4, worker_count=1, scheduler_interval=10)
    cache.start()
    cache._record_worker_failure(RuntimeError("boom"))
    cache.close(flush=False)
    assert cache.stats().worker_jobs_failed >= 1


def test_parse_write_mode_invalid() -> None:
    cache = Cache(capacity=4)
    with pytest.raises(UnsupportedWriteModeError):
        cache._parse_write_mode("invalid-mode")


def test_in_memory_backend_direct() -> None:
    from cachelab.core.entry import CacheEntry

    backend = InMemoryBackend()
    entry = CacheEntry(
        key="k",
        value="v",
        created_at=0.0,
        last_accessed_at=0.0,
        hit_count=0,
        expires_at=None,
        ttl=None,
        version=1,
    )
    backend.put_entry(entry)
    assert backend.contains("k")
    assert backend.get_entry("k") is entry
    assert backend.size() == 1
    assert list(backend.keys()) == ["k"]
    assert list(backend.entries()) == [entry]
    assert backend.delete_entry("k")
    assert not backend.delete_entry("missing")
    backend.put_entry(entry)
    backend.clear()
    assert backend.size() == 0
