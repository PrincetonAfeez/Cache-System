"""Minimal CacheLab library usage: context manager, TTL, and stats."""

from __future__ import annotations

from cachelab import Cache


def main() -> None:
    with Cache(capacity=100, policy="lru", shard_count=4, default_ttl=60) as cache:
        cache.put("session:1", {"user": "Ada"})
        profile = cache.get_or_compute("profile:1", lambda: {"name": "Ada", "role": "engineer"})
        print("profile:", profile)
        print(cache.stats())


if __name__ == "__main__":
    main()
