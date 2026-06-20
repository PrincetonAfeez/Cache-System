""" Patterns utilities for CacheLab """

from __future__ import annotations

import random
from collections.abc import Iterator


def key_stream(pattern: str, requests: int, *, capacity: int, seed: int = 1) -> Iterator[str]:
    rng = random.Random(seed)
    normalized = pattern.lower().replace("-", "_")
    universe = max(capacity * 4, 16)
    if normalized == "uniform":
        for _ in range(requests):
            yield f"k{rng.randrange(universe)}"
        return
    if normalized in {"zipfian", "hotspot"}:
        hot = [f"k{i}" for i in range(max(1, capacity // 5))]
        cold = [f"k{i}" for i in range(max(1, capacity // 5), universe)]
        for _ in range(requests):
            if rng.random() < 0.82:
                yield rng.choice(hot)
            else:
                yield rng.choice(cold)
        return
    if normalized in {"sequential", "sequential_scan"}:
        for index in range(requests):
            yield f"k{index}"
        return
    if normalized in {"looping", "looping_working_set"}:
        # Keep the working set just inside capacity so a recency policy can hold
        # the whole loop (high hit ratio); contrast with the "sequential" scan,
        # whose unique keys never repeat and defeat every policy.
        working_set = max(1, capacity - max(1, capacity // 5))
        for index in range(requests):
            yield f"k{index % working_set}"
        return
    if normalized in {"mixed", "mixed_read_write"}:
        for index in range(requests):
            if index % 5 == 0:
                yield f"write:k{rng.randrange(universe)}"
            else:
                yield f"k{rng.randrange(universe)}"
        return
    raise ValueError(f"unknown workload pattern: {pattern}")
