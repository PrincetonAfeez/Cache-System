""" Test patterns """

from __future__ import annotations

import pytest

from cachelab.workloads.patterns import key_stream


def _collect(pattern: str, requests: int = 200, capacity: int = 20, seed: int = 1) -> list[str]:
    return list(key_stream(pattern, requests, capacity=capacity, seed=seed))


def test_uniform_is_deterministic_for_a_seed() -> None:
    assert _collect("uniform") == _collect("uniform")
    keys = _collect("uniform", requests=50)
    assert len(keys) == 50
    assert all(key.startswith("k") for key in keys)


def test_different_seeds_produce_different_streams() -> None:
    assert _collect("uniform", seed=1) != _collect("uniform", seed=2)


def test_sequential_keys_are_unique_and_ordered() -> None:
    assert _collect("sequential", requests=50) == [f"k{i}" for i in range(50)]


def test_looping_working_set_stays_inside_capacity() -> None:
    capacity = 20
    keys = _collect("looping", requests=500, capacity=capacity)
    distinct = {int(key[1:]) for key in keys}
    working_set = max(1, capacity - max(1, capacity // 5))
    assert max(distinct) < working_set
    assert len(distinct) == working_set  # the whole loop is visited


def test_hotspot_is_skewed_toward_hot_keys() -> None:
    capacity = 20
    keys = _collect("hotspot", requests=2000, capacity=capacity)
    hot = {f"k{i}" for i in range(max(1, capacity // 5))}
    hot_hits = sum(1 for key in keys if key in hot)
    assert hot_hits > len(keys) * 0.6  # configured at ~0.82


def test_zipfian_and_hotspot_share_a_distribution() -> None:
    assert _collect("zipfian", seed=7) == _collect("hotspot", seed=7)


def test_mixed_emits_write_markers() -> None:
    keys = _collect("mixed", requests=50)
    writes = [key for key in keys if key.startswith("write:")]
    reads = [key for key in keys if not key.startswith("write:")]
    assert len(writes) == 10  # every 5th request of 50
    assert reads


@pytest.mark.parametrize(
    "alias,canonical",
    [
        ("sequential_scan", "sequential"),
        ("sequential-scan", "sequential"),
        ("looping_working_set", "looping"),
        ("mixed_read_write", "mixed"),
        ("HOTSPOT", "hotspot"),
    ],
)
def test_aliases_and_casing_match_canonical(alias: str, canonical: str) -> None:
    assert _collect(alias, requests=30) == _collect(canonical, requests=30)


def test_unknown_pattern_raises() -> None:
    with pytest.raises(ValueError):
        list(key_stream("bogus", 5, capacity=10))
