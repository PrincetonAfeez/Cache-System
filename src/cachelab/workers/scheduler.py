""" Scheduler utilities for CacheLab """

from __future__ import annotations

import logging
import threading

from cachelab.core.clock import Clock
from cachelab.workers.messages import ExpireShard
from cachelab.workers.queue import CacheJobQueue


class ExpirationScheduler:
    def __init__(
        self,
        interval: float,
        shard_count: int,
        job_queue: CacheJobQueue,
        clock: Clock,
        logger: logging.Logger,
    ) -> None:
        self.interval = interval
        self.shard_count = shard_count
        self.job_queue = job_queue
        self.clock = clock
        self.logger = logger
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="cachelab-scheduler", daemon=False)
            self._thread.start()

    def tick_once(self) -> None:
        # Expiration jobs are non-critical: a full queue drops them (counted in
        # queue stats) rather than blocking request threads. Lazy expiration
        # still keeps reads correct in the meantime.
        for shard_index in range(self.shard_count):
            self.job_queue.put(ExpireShard(shard_index), critical=False)
        self.logger.info("cachelab_event scheduler_tick shards=%s", self.shard_count)

    def stop(self, timeout: float) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def alive(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def thread(self) -> threading.Thread | None:
        return self._thread

    def _run(self) -> None:
        self.logger.info("cachelab_event scheduler_start")
        while not self._stop.wait(self.interval):
            self.tick_once()
        self.logger.info("cachelab_event scheduler_stop")
