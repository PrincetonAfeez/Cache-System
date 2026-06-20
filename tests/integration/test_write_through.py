""" Test write through """

from __future__ import annotations

import pytest

from cachelab import Cache
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode


def test_write_through_persists_before_returning() -> None:
    backend = SlowDictBackend()
    cache = Cache(capacity=2, write_mode=WriteMode.WRITE_THROUGH.value, source_backend=backend)
    cache.put("a", "one")
    assert backend.get_value("a") == "one"
    cache.delete("a")
    assert backend.get_value("a") is None


def test_write_through_surfaces_backend_failure_to_caller() -> None:
    # A write-through put writes the source first; if that fails the error must
    # reach the caller and the cache must not be updated.
    backend = SlowDictBackend()
    backend.fail_next(1)
    cache = Cache(capacity=4, write_mode=WriteMode.WRITE_THROUGH.value, source_backend=backend)
    with pytest.raises(OSError):
        cache.put("a", "one")
    assert cache.get("a") is None
