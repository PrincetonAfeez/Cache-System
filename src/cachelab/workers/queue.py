""" Queue utilities for CacheLab """

from __future__ import annotations

import queue
import threading
import time

from cachelab.workers.messages import Job


class CacheJobQueue:
    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.Queue[Job] = queue.Queue(maxsize=maxsize)
        self._dropped = 0
        self._dropped_lock = threading.Lock()

    def put(self, job: Job, *, critical: bool, timeout: float | None = None) -> bool:
        try:
            if critical:
                self._queue.put(job, block=True, timeout=timeout)
            else:
                self._queue.put_nowait(job)
            return True
        except queue.Full:
            with self._dropped_lock:
                self._dropped += 1
            return False

    def offer(self, job: Job) -> bool:
        """Best-effort enqueue that never counts as a dropped job.

        Used for shutdown sentinels: failure to enqueue is harmless because the
        worker pool's stop event guarantees workers exit regardless.
        """
        try:
            self._queue.put_nowait(job)
            return True
        except queue.Full:
            return False

    def get(self, timeout: float | None = None) -> Job:
        return self._queue.get(block=True, timeout=timeout)

    def task_done(self) -> None:
        self._queue.task_done()

    def drain(self) -> int:
        """Discard any remaining items (e.g. leftover stop sentinels after a
        shutdown) so the queue reports an empty, settled state. Returns the count
        removed."""
        removed = 0
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            self._queue.task_done()
            removed += 1
        return removed

    def join_until(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while self.unfinished_tasks > 0:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return True

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    @property
    def dropped(self) -> int:
        with self._dropped_lock:
            return self._dropped

    @property
    def unfinished_tasks(self) -> int:
        return self._queue.unfinished_tasks
