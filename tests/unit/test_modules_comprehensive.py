""" Test modules comprehensive """

from __future__ import annotations

import logging

import pytest

import cachelab
from cachelab.core.clock import FakeClock, MonotonicClock
from cachelab.core.exceptions import ConfigurationError
from cachelab.observability.logging import get_logger, log_event
from cachelab.observability.tables import format_table
from cachelab.policies.base import make_policy
from cachelab.policies.fifo import FIFOPolicy
from cachelab.policies.lfu import LFUPolicy
from cachelab.policies.lru import LRUPolicy
from cachelab.storage import InMemoryBackend, SlowDictBackend, StorageBackend, WriteMode
from cachelab.workloads.patterns import key_stream


def test_package_exports() -> None:
    assert cachelab.Cache is not None
    assert cachelab.CacheConfig is not None
    assert cachelab.ValidationError is not None
    assert cachelab.__version__


def test_monotonic_clock_now_and_sleep() -> None:
    clock = MonotonicClock()
    before = clock.now()
    clock.sleep(0)
    assert clock.now() >= before


def test_fake_clock_rejects_negative_advance() -> None:
    clock = FakeClock(start=10.0)
    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.advance(-1)


def test_fake_clock_sleep_advances_time() -> None:
    clock = FakeClock(start=0.0)
    clock.sleep(5)
    assert clock.now() == 5.0


def test_log_event_emits_when_info_enabled(caplog: pytest.LogCaptureFixture) -> None:
    logger = get_logger()
    with caplog.at_level(logging.INFO, logger="cachelab"):
        log_event(logger, "test_event", key="k", shard=1)
    assert "cachelab_event test_event" in caplog.text
    assert "key='k'" in caplog.text


def test_log_event_skips_formatting_when_disabled() -> None:
    logger = get_logger()
    logger.setLevel(logging.WARNING)
    log_event(logger, "skipped", key="k")


def test_make_policy_returns_all_policies() -> None:
    assert make_policy("lru").name == "lru"
    assert make_policy("LFU").name == "lfu"
    assert make_policy("fifo").name == "fifo"
    with pytest.raises(ConfigurationError):
        make_policy("random")


def test_fifo_clear_and_metadata() -> None:
    policy = FIFOPolicy()
    policy.on_put("a")
    policy.on_put("b")
    assert len(policy) == 2
    assert policy.metadata_size() == 2
    policy.clear()
    assert len(policy) == 0
    assert policy.evict_candidate() is None


def test_lfu_evict_returns_none_when_bucket_empty() -> None:
    policy = LFUPolicy()
    policy.on_put("a")
    policy._freq_to_keys[1].clear()
    assert policy.evict_candidate() is None


def test_lfu_on_delete_unknown_key_is_noop() -> None:
    policy = LFUPolicy()
    policy.on_delete("missing")


def test_lru_policy_metadata() -> None:
    policy = LRUPolicy()
    policy.on_put("a")
    policy.on_get("a")
    assert policy.evict_candidate() == "a"
    assert policy.metadata_size() >= 1


def test_format_table_renders_rows() -> None:
    table = format_table(["a", "b"], [["1", "2"]])
    assert "1" in table
    assert "2" in table


def test_storage_package_exports() -> None:
    assert WriteMode.CACHE_ONLY.value == "cache-only"
    assert issubclass(InMemoryBackend, StorageBackend)
    backend = SlowDictBackend(delay=0.0)
    backend.put_value("k", "v")
    assert backend.get_value("k") == "v"


def test_key_stream_patterns_cover_all_names() -> None:
    for pattern in ("uniform", "hotspot", "sequential", "looping", "mixed"):
        keys = list(key_stream(pattern, 20, capacity=10, seed=1))
        assert len(keys) == 20
