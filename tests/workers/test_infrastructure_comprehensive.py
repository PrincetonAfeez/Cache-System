""" Test infrastructure comprehensive """

from __future__ import annotations

import logging
import threading
import time
from unittest.mock import Mock

import pytest

from cachelab.core.exceptions import ValidationError
from cachelab.workers.messages import FlushWriteBack, StopWorker
from cachelab.workers.queue import CacheJobQueue
from cachelab.workers.scheduler import ExpirationScheduler
from cachelab.workers.shutdown import join_all
from cachelab.workers.worker_pool import WorkerPool
from cachelab.workers.write_back_worker import apply_write_back, is_stale_write_back


def test_queue_join_until_times_out() -> None:
    job_queue = CacheJobQueue(maxsize=4)
    job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    assert job_queue.join_until(0.01) is False


def test_queue_drain_and_depth() -> None:
    job_queue = CacheJobQueue(maxsize=2)
    job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    assert job_queue.depth == 1
    assert job_queue.drain() == 1
    assert job_queue.depth == 0


def test_queue_offer_returns_false_when_full() -> None:
    job_queue = CacheJobQueue(maxsize=1)
    job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    assert job_queue.offer(object()) is False  # type: ignore[arg-type]


def test_worker_pool_start_with_zero_count_is_noop() -> None:
    job_queue = CacheJobQueue()
    pool = WorkerPool("test", 0, job_queue, lambda job: None, lambda exc: None, logging.getLogger("test"))
    pool.start()
    assert pool.started is False
    pool.stop(1.0)


def test_worker_pool_stop_drains_without_start() -> None:
    job_queue = CacheJobQueue(maxsize=2)
    job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    pool = WorkerPool("test", 1, job_queue, lambda job: None, lambda exc: None, logging.getLogger("test"))
    pool.stop(1.0)
    assert job_queue.depth == 0


def test_worker_pool_idle_stop_on_empty_queue(caplog: pytest.LogCaptureFixture) -> None:
    job_queue = CacheJobQueue(maxsize=4)
    logger = logging.getLogger("test-worker")
    pool = WorkerPool("test", 1, job_queue, lambda job: None, lambda exc: None, logger)
    pool.start()
    pool.stop(2.0)
    assert pool.alive_threads() == []


def test_worker_pool_handler_failure_invokes_callback() -> None:
    failures: list[BaseException] = []
    job_queue = CacheJobQueue(maxsize=4)

    def handler(job: object) -> None:
        raise RuntimeError("handler failed")

    pool = WorkerPool(
        "test",
        1,
        job_queue,
        handler,
        failures.append,
        logging.getLogger("test"),
    )
    pool.start()
    job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    deadline = time.monotonic() + 2.0
    while not failures and time.monotonic() < deadline:
        time.sleep(0.01)
    pool.stop(2.0)
    assert failures


def test_scheduler_double_start_is_idempotent() -> None:
    job_queue = CacheJobQueue(maxsize=8)
    scheduler = ExpirationScheduler(
        interval=10.0,
        shard_count=2,
        job_queue=job_queue,
        clock=Mock(now=lambda: 0.0, sleep=lambda s: None),
        logger=logging.getLogger("test"),
    )
    scheduler.start()
    first = scheduler.thread
    scheduler.start()
    assert scheduler.thread is first
    scheduler.stop(1.0)


def test_scheduler_tick_once_enqueues_jobs() -> None:
    job_queue = CacheJobQueue(maxsize=8)
    scheduler = ExpirationScheduler(
        interval=10.0,
        shard_count=3,
        job_queue=job_queue,
        clock=Mock(now=lambda: 0.0, sleep=lambda s: None),
        logger=logging.getLogger("test"),
    )
    scheduler.tick_once()
    assert job_queue.depth == 3


def test_join_all_returns_survivors() -> None:
    thread = threading.Thread(target=lambda: time.sleep(0.2))
    thread.start()
    survivors = join_all([thread], timeout=0.01)
    assert survivors
    thread.join(timeout=1.0)


def test_is_stale_write_back_delete_cases() -> None:
    job = FlushWriteBack(
        shard_index=0,
        key="k",
        value=None,
        version=2,
        operation="delete",
        retries_left=0,
    )
    assert is_stale_write_back({ "k": 3 }, {}, job)
    assert is_stale_write_back({}, { "k": 1 }, job)


def test_is_stale_write_back_unknown_operation() -> None:
    job = FlushWriteBack(
        shard_index=0,
        key="k",
        value="v",
        version=1,
        operation="patch",
        retries_left=0,
    )
    assert is_stale_write_back({}, {}, job)


def test_apply_write_back_put_and_delete() -> None:
    backend = Mock()
    put_job = FlushWriteBack(
        shard_index=0,
        key="k",
        value="v",
        version=1,
        operation="put",
        retries_left=0,
    )
    delete_job = FlushWriteBack(
        shard_index=0,
        key="k",
        value=None,
        version=2,
        operation="delete",
        retries_left=0,
    )
    apply_write_back(backend, put_job)
    apply_write_back(backend, delete_job)
    backend.put_value.assert_called_once_with("k", "v")
    backend.delete_value.assert_called_once_with("k")


def test_apply_write_back_unknown_operation_raises() -> None:
    job = FlushWriteBack(
        shard_index=0,
        key="k",
        value="v",
        version=1,
        operation="noop",
        retries_left=0,
    )
    with pytest.raises(ValidationError, match="unknown write-back operation"):
        apply_write_back(Mock(), job)


def test_worker_stop_sentinel_exits_loop() -> None:
    job_queue = CacheJobQueue(maxsize=4)
    seen: list[str] = []

    def handler(job: object) -> None:
        seen.append("handled")

    pool = WorkerPool("test", 1, job_queue, handler, lambda exc: None, logging.getLogger("test"))
    pool.start()
    job_queue.put(StopWorker(), critical=False)
    pool.stop(2.0)
    assert seen == []
