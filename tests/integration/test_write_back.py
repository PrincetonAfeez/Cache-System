""" Test write back """

from __future__ import annotations

from cachelab import Cache, FakeClock
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode


def test_write_back_flushes_in_worker_on_close() -> None:
    backend = SlowDictBackend()
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=1,
        source_backend=backend,
    )
    cache.start()
    cache.put("a", "one")
    cache.close()
    assert backend.get_value("a") == "one"


def test_write_back_retry_is_counted() -> None:
    # A FakeClock makes the retry backoff advance virtual time instead of
    # sleeping for real, keeping this correctness test deterministic and fast.
    backend = SlowDictBackend()
    backend.fail_next(1)
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=1,
        source_backend=backend,
        clock=FakeClock(),
    )
    cache.start()
    cache.put("a", "one")
    cache.close()
    assert backend.get_value("a") == "one"
    assert cache.stats().write_back_retries >= 1
