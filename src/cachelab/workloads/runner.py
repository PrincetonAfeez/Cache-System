""" Runner utilities for CacheLab """

from __future__ import annotations

from dataclasses import asdict

from cachelab.core.cache import Cache
from cachelab.workloads.patterns import key_stream


def run_simulation(
    *,
    policy: str,
    pattern: str,
    capacity: int,
    requests: int,
    seed: int = 1,
    shards: int = 1,
) -> dict[str, object]:
    # Default to a single shard so the reported hit ratio reflects the policy
    # itself rather than capacity split across N independent sub-caches.
    cache = Cache(capacity=capacity, policy=policy, shard_count=shards)
    writes = 0
    for index, raw_key in enumerate(key_stream(pattern, requests, capacity=capacity, seed=seed)):
        if raw_key.startswith("write:"):
            key = raw_key.split(":", 1)[1]
            cache.put(key, f"value-{index}")
            writes += 1
            continue
        if cache.get(raw_key) is None:
            cache.put(raw_key, f"value-{raw_key}")
    stats = cache.stats()
    return {
        "policy": policy,
        "pattern": pattern,
        "requests": requests,
        "writes": writes,
        "hits": stats.hits,
        "misses": stats.misses,
        "hit_ratio": round(stats.hit_ratio, 4),
        "evictions": stats.evictions,
        "expirations": stats.expirations,
        "size": stats.size,
        "shards": [asdict(shard) for shard in stats.shards],
    }
