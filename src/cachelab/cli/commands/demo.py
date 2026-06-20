""" Demo commands for the CLI """

from __future__ import annotations

import threading
import time
from typing import Callable

from cachelab.cli.commands.render import print_simulation, stats_table
from cachelab.core.cache import Cache
from cachelab.core.clock import FakeClock
from cachelab.observability.tables import format_table
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode
from cachelab.teaching import (
    unsafe_race_demo,
    unsafe_singleflight_demo,
    unsafe_wall_clock_ttl_demo,
    unsafe_write_back_resurrection_demo,
)
from cachelab.workers.messages import ExpireShard
from cachelab.workloads.benchmark import benchmark_policies

_ALL_DEMOS = [
    "worker-queue",
    "backpressure",
    "ttl-lazy",
    "ttl-active",
    "single-flight",
    "sharding",
    "write-through-vs-write-back",
    "write-back-retry",
    "unsafe-race",
    "unsafe-single-flight",
    "unsafe-write-back-resurrection",
    "wall-clock-ttl-bug",
]


def run_demo(name: str) -> int:
    if name == "all":
        for demo_name in _ALL_DEMOS:
            print(f"\n== {demo_name} ==")
            run_demo(demo_name)
        print("\n== policy benchmark ==")
        print_simulation(
            benchmark_policies(policies=["fifo", "lru", "lfu"], pattern="hotspot", capacity=50, requests=5000)
        )
        return 0
    handler = _DEMOS.get(name)
    if handler is None:
        raise ValueError(f"unknown demo: {name}")
    return handler()


def _demo_ttl_lazy() -> int:
    clock = FakeClock()
    cache = Cache(capacity=2, default_ttl=5, clock=clock)
    cache.put("token", "abc")
    clock.advance(6)
    print(f"lazy get after ttl: {cache.get('token')!r}")
    print(stats_table(cache))
    return 0


def _demo_ttl_active() -> int:
    cache = Cache(capacity=4, worker_count=1, scheduler_interval=0.02)
    cache.start()
    cache.put("short", "lived", ttl=0.01)
    time.sleep(0.08)
    size_after = cache.size()
    cache.close()
    print(f"active expiration size: {size_after}")
    print(stats_table(cache))
    return 0


def _demo_worker_queue() -> int:
    # Normal flow: the scheduler enqueues ExpireShard jobs and the worker pool
    # drains them; expiration happens off the request path with no drops.
    clock = FakeClock()
    cache = Cache(capacity=8, worker_count=2, queue_size=64, scheduler_interval=10, clock=clock)
    cache.start()
    for index in range(8):
        cache.put(f"k{index}", index, ttl=1)
    clock.advance(2)
    cache.scheduler_tick()
    cache.job_queue.join_until(1)
    size_after = cache.size()
    cache.close(flush=False)
    print(f"worker-queue: 8 entries expired by background workers; size now {size_after}")
    print(stats_table(cache))
    return 0


def _demo_backpressure() -> int:
    # A tiny bounded queue with no consumers fills immediately. Non-critical
    # jobs are dropped and counted (never block the caller); critical write-back
    # jobs instead raise QueueBackpressureError so durable work is never lost.
    cache = Cache(capacity=8, worker_count=0, queue_size=1)
    offered, accepted = 20, 0
    for _ in range(offered):
        if cache.job_queue.put(ExpireShard(0), critical=False):
            accepted += 1
    print(
        f"backpressure: queue_size=1, offered={offered}, accepted={accepted}, "
        f"dropped={cache.stats().queue_dropped}"
    )
    print("critical jobs raise QueueBackpressureError rather than dropping silently")
    print(stats_table(cache))
    return 0


def _demo_single_flight() -> int:
    cache = Cache(capacity=4, shard_count=2)
    calls = 0
    lock = threading.Lock()
    barrier = threading.Barrier(40)

    def loader() -> str:
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.01)
        return "loaded-once"

    def read() -> None:
        barrier.wait()
        cache.get_or_compute("same", loader)

    threads = [threading.Thread(target=read) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print(f"loader calls under contention: {calls}")
    return 0


def _demo_sharding() -> int:
    cache = Cache(capacity=200, shard_count=8)
    threads = [threading.Thread(target=_traffic, args=(cache, index)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print(stats_table(cache))
    return 0


def _demo_write_modes() -> int:
    through_backend = SlowDictBackend(delay=0.002)
    back_backend = SlowDictBackend(delay=0.002)
    through = Cache(capacity=100, write_mode=WriteMode.WRITE_THROUGH.value, source_backend=through_backend)
    back = Cache(
        capacity=100,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=1,
        source_backend=back_backend,
    )
    back.start()
    through_time = _time_puts(through, 50)
    back_time = _time_puts(back, 50)
    back.close()
    print(
        format_table(
            ["mode", "seconds", "persisted"],
            [
                ["write-through", through_time, len(through_backend.snapshot())],
                ["write-back", back_time, len(back_backend.snapshot())],
            ],
        )
    )
    return 0


def _demo_write_back_retry() -> int:
    backend = SlowDictBackend()
    backend.fail_next(1)
    cache = Cache(
        capacity=4,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=1,
        source_backend=backend,
    )
    cache.start()
    cache.put("retry", "eventually")
    cache.close()
    print(stats_table(cache))
    print(f"backend value: {backend.get_value('retry')}")
    return 0


def _demo_unsafe_race() -> int:
    print(unsafe_race_demo())
    return 0


def _demo_unsafe_single_flight() -> int:
    print(unsafe_singleflight_demo())
    return 0


def _demo_unsafe_write_back_resurrection() -> int:
    print(unsafe_write_back_resurrection_demo())
    return 0


def _demo_wall_clock_ttl_bug() -> int:
    print(unsafe_wall_clock_ttl_demo())
    return 0


def _traffic(cache: Cache, worker: int) -> None:
    for index in range(500):
        key = f"{worker}:{index % 80}"
        cache.put(key, index)
        cache.contains(key)
        cache.get(key)


def _time_puts(cache: Cache, count: int) -> float:
    start = time.perf_counter()
    for index in range(count):
        cache.put(f"k{index}", f"v{index}")
    return round(time.perf_counter() - start, 5)


_DEMOS: dict[str, Callable[[], int]] = {
    "ttl-lazy": _demo_ttl_lazy,
    "ttl-active": _demo_ttl_active,
    "worker-queue": _demo_worker_queue,
    "backpressure": _demo_backpressure,
    "single-flight": _demo_single_flight,
    "sharding": _demo_sharding,
    "write-through-vs-write-back": _demo_write_modes,
    "write-back-retry": _demo_write_back_retry,
    "unsafe-race": _demo_unsafe_race,
    "unsafe-single-flight": _demo_unsafe_single_flight,
    "unsafe-write-back-resurrection": _demo_unsafe_write_back_resurrection,
    "wall-clock-ttl-bug": _demo_wall_clock_ttl_bug,
}
