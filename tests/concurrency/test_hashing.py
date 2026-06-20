""" Test hashing """

from __future__ import annotations

from cachelab import Cache
from cachelab.concurrency.hashing import stable_hash
from cachelab.concurrency.shards import shard_capacities


def test_stable_hash_is_deterministic() -> None:
    assert stable_hash("user:1") == stable_hash("user:1")
    assert stable_hash(("a", 1)) == stable_hash(("a", 1))


def test_numeric_equal_keys_route_to_the_same_shard() -> None:
    # 1 == 1.0 == True in Python and share one dict slot; they must not miss each
    # other across shards.
    cache = Cache(capacity=64, shard_count=8)
    cache.put(1, "one")
    assert cache.get(1.0) == "one"
    assert cache.get(True) == "one"
    assert cache.contains(1.0)


def test_shard_capacities_divides_total_predictably() -> None:
    assert shard_capacities(10, 1) == [10]
    assert shard_capacities(10, 2) == [5, 5]
    assert shard_capacities(10, 3) == [4, 3, 3]  # remainder assigned to low indexes
    assert sum(shard_capacities(128, 7)) == 128
