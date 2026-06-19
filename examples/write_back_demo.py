"""Write-back mode: cache returns immediately; workers flush on close."""

from __future__ import annotations

from cachelab import Cache
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode


def main() -> None:
    backend = SlowDictBackend(delay=0.01)
    cache = Cache(
        capacity=8,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=1,
        source_backend=backend,
    )
    cache.start()
    try:
        cache.put("user:1", "Ada")
        snapshot = cache.inspect("user:1")
        print("in cache:", snapshot.value if snapshot else None)
        print("dirty before close:", snapshot.dirty if snapshot else None)
    finally:
        cache.close(flush=True)
    print("on backend after close:", backend.get_value("user:1"))
    print("stats:", cache.stats())


if __name__ == "__main__":
    main()
