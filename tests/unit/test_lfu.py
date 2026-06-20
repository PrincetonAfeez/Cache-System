""" Test LFU """

from __future__ import annotations

from cachelab import Cache
from cachelab.policies.lfu import LFUPolicy


def test_lfu_policy_get_or_delete_on_missing_key_is_noop() -> None:
    policy = LFUPolicy()
    policy.on_get("absent")
    policy.on_delete("absent")
    assert len(policy) == 0
    assert policy.evict_candidate() is None  # empty -> min_freq 0


def test_lfu_policy_delete_recomputes_min_freq_when_bucket_empties() -> None:
    policy = LFUPolicy()
    policy.on_put("a")
    policy.on_put("b")
    policy.on_get("a")  # a -> freq 2; b stays at freq 1 (min_freq)
    policy.on_delete("b")  # frequency-1 bucket empties; min_freq must rise to 2
    assert policy.evict_candidate() == "a"
    assert policy.metadata_size() >= 1


def test_lfu_policy_bump_raises_min_freq_when_only_key_advances() -> None:
    policy = LFUPolicy()
    policy.on_put("a")
    policy.on_get("a")  # sole frequency-1 bucket empties; min_freq -> 2
    assert policy.evict_candidate() == "a"


def test_lfu_policy_reput_existing_key_increases_its_frequency() -> None:
    policy = LFUPolicy()
    policy.on_put("a")
    policy.on_put("b")
    policy.on_put("a")  # re-put of a live key bumps frequency, not a duplicate
    assert policy.evict_candidate() == "b"  # b is now the least frequent
    assert len(policy) == 2


def test_lfu_policy_clear_resets_all_state() -> None:
    policy = LFUPolicy()
    policy.on_put("a")
    policy.on_put("b")
    policy.clear()
    assert len(policy) == 0
    assert policy.metadata_size() == 0
    assert policy.evict_candidate() is None


def test_lfu_evicts_lowest_frequency() -> None:
    cache = Cache(capacity=2, policy="lfu", shard_count=1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_lfu_ties_break_by_recency_inside_frequency() -> None:
    cache = Cache(capacity=2, policy="lfu", shard_count=1)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
