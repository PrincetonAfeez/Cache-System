""" Test benchmark """

from __future__ import annotations

from typing import cast

from cachelab.workloads.benchmark import benchmark_policies
from cachelab.workloads.runner import run_simulation


def test_run_simulation_counts_writes_for_mixed_pattern() -> None:
    result = run_simulation(policy="lru", pattern="mixed", capacity=20, requests=100, seed=1)
    assert result["writes"] == 20  # every 5th request of 100
    assert result["policy"] == "lru"
    assert result["requests"] == 100
    assert isinstance(result["hit_ratio"], float)


def test_run_simulation_sequential_scan_has_no_hits() -> None:
    result = run_simulation(policy="fifo", pattern="sequential", capacity=10, requests=200)
    assert result["hits"] == 0
    assert cast(int, result["size"]) <= 10


def test_run_simulation_is_deterministic_for_a_seed() -> None:
    a = run_simulation(policy="lru", pattern="hotspot", capacity=20, requests=500, seed=3)
    b = run_simulation(policy="lru", pattern="hotspot", capacity=20, requests=500, seed=3)
    assert a["hits"] == b["hits"]
    assert a["misses"] == b["misses"]


def test_benchmark_policies_returns_a_row_per_policy_with_timings() -> None:
    rows = benchmark_policies(policies=["lru", "fifo"], pattern="hotspot", capacity=20, requests=200)
    assert [row["policy"] for row in rows] == ["lru", "fifo"]
    for row in rows:
        assert "seconds" in row
        assert "requests_per_second" in row
        assert row["requests"] == 200
