""" Worker pool utilities for CacheLab """

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from cachelab.workers.messages import Job, StopWorker
from cachelab.workers.queue import CacheJobQueue
from cachelab.workers.shutdown import join_all

# How long an idle worker blocks on the queue before re-checking the stop event.
# This is a blocking wait on a real queue operation (not a busy-spin): an
# enqueued job wakes the worker immediately; the timeout only bounds how long a
# fully idle worker waits before noticing a stop signal.
_IDLE_POLL_SECONDS = 0.25


class WorkerPool:
    def __init__(
        self,
        name: str,
        count: int,
        job_queue: CacheJobQueue,
        handler: Callable[[Job], None],
        on_failure: Callable[[BaseException], None],
        logger: logging.Logger,
    ) -> None:
        self.name = name
        self.count = count
        self.job_queue = job_queue
        self.handler = handler
        self.on_failure = on_failure
        self.logger = logger
        self._threads: list[threading.Thread] = []
        self._started = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def started(self) -> bool:
        with self._lock:
            return self._started

    def start(self) -> None:
        with self._lock:
            if self._started or self.count == 0:
                return
            self._stop_event.clear()
            self._started = True
            for index in range(self.count):
                thread = threading.Thread(
                    target=self._run,
                    name=f"{self.name}-{index}",
                    daemon=False,
                )
                self._threads.append(thread)
                thread.start()

    def stop(self, timeout: float) -> None:
        with self._lock:
            started = self._started
            threads = list(self._threads)
        if started:
            # The stop event is the guarantee that every worker exits even if a
            # bounded queue is full; StopWorker sentinels are a best-effort nudge so
            # idle workers wake promptly instead of waiting for the idle timeout.
            self._stop_event.set()
            for _ in threads:
                self.job_queue.offer(StopWorker())
            survivors = join_all(threads, timeout)
            with self._lock:
                self._started = False
                self._threads = survivors
        # Always settle the queue (including when workers were never started).
        self.job_queue.drain()

    def alive_threads(self) -> list[threading.Thread]:
        with self._lock:
            return [thread for thread in self._threads if thread.is_alive()]

    def _run(self) -> None:
        self.logger.info("cachelab_event worker_start name=%s", threading.current_thread().name)
        while True:
            try:
                job = self.job_queue.get(timeout=_IDLE_POLL_SECONDS)
            except queue.Empty:
                if self._stop_event.is_set():
                    self.logger.info(
                        "cachelab_event worker_stop name=%s", threading.current_thread().name
                    )
                    return
                continue
            try:
                if isinstance(job, StopWorker):
                    self.logger.info(
                        "cachelab_event worker_stop name=%s", threading.current_thread().name
                    )
                    return
                self.handler(job)
            except BaseException as exc:  # pragma: no cover - defensive isolation for worker loops.
                self.on_failure(exc)
                self.logger.exception("cachelab_event worker_failure")
            finally:
                self.job_queue.task_done()
