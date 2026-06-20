""" Test tombstones """

from __future__ import annotations

from cachelab import Cache
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode
from cachelab.workers.messages import FlushWriteBack


def test_delete_tombstone_blocks_stale_put_resurrection() -> None:
    backend = SlowDictBackend()
    cache = Cache(capacity=4, write_mode=WriteMode.WRITE_BACK.value, source_backend=backend)
    cache.put("a", "v1")
    stale_put = cache.job_queue.get()
    cache.job_queue.task_done()
    assert isinstance(stale_put, FlushWriteBack)
    cache.delete("a")
    # Replaying the old put job must not resurrect the deleted value.
    cache._flush_write_back_job(stale_put)
    cache.close()
    assert backend.get_value("a") is None


def test_tombstones_and_versions_are_pruned_after_flush() -> None:
    # The metadata that guards against resurrection must not accumulate forever:
    # once every flush for a key has completed, its marks are dropped.
    backend = SlowDictBackend()
    cache = Cache(
        capacity=64,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=1,
        source_backend=backend,
    )
    cache.start()
    for index in range(50):
        cache.put(f"k{index}", index)
    for index in range(50):
        cache.delete(f"k{index}")
    assert cache.job_queue.join_until(5)
    cache.close()
    for shard in cache._shards:
        assert shard.tombstones == {}
        assert shard.version_marks == {}
        assert shard.pending_flushes == {}
