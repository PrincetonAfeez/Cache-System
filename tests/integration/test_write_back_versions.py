""" Test write back versions """

from __future__ import annotations

from cachelab import Cache
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode
from cachelab.workers.messages import FlushWriteBack


def test_stale_write_back_put_cannot_overwrite_newer_value() -> None:
    backend = SlowDictBackend()
    cache = Cache(capacity=4, write_mode=WriteMode.WRITE_BACK.value, source_backend=backend)
    cache.put("a", "old")
    stale_job = cache.job_queue.get()
    cache.job_queue.task_done()
    assert isinstance(stale_job, FlushWriteBack)
    cache.put("a", "new")
    cache._flush_write_back_job(stale_job)
    cache.close()
    assert backend.get_value("a") == "new"
    assert cache.stats().stale_write_back_jobs_skipped >= 1


def test_tombstone_prevents_write_back_resurrection() -> None:
    backend = SlowDictBackend()
    cache = Cache(capacity=4, write_mode=WriteMode.WRITE_BACK.value, source_backend=backend)
    cache.put("a", "old")
    stale_job = cache.job_queue.get()
    cache.job_queue.task_done()
    cache.delete("a")
    assert isinstance(stale_job, FlushWriteBack)
    cache._flush_write_back_job(stale_job)
    cache.close()
    assert backend.get_value("a") is None
    assert cache.stats().stale_write_back_jobs_skipped >= 1
