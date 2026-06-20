""" Benchmark utilities for CacheLab """

from __future__ import annotations

import time

from cachelab.workloads.runner import run_simulation


def benchmark_policies(
    *,
    policies: list[str],
    pattern: str,
    capacity: int,
    requests: int,
    seed: int = 1,
    shards: int = 1,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for policy in policies:
        started = time.perf_counter()
        result = run_simulation(
            policy=policy,
            pattern=pattern,
            capacity=capacity,
            requests=requests,
            seed=seed,
            shards=shards,
        )
        elapsed = time.perf_counter() - started
        result["seconds"] = round(elapsed, 6)
        result["requests_per_second"] = round(requests / elapsed, 2) if elapsed else 0
        rows.append(result)
    return rows
