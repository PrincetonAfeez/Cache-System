""" Shutdown utilities for CacheLab """

from __future__ import annotations

import threading

from cachelab.workers.messages import StopWorker

__all__ = ["StopWorker", "join_all"]


def join_all(threads: list[threading.Thread], timeout: float) -> list[threading.Thread]:
    """Join every thread (best-effort) and return the ones still alive.

    Returning the survivors lets the caller assert the thread-lifecycle
    invariant: a clean ``close()`` must leave this list empty.
    """
    for thread in threads:
        thread.join(timeout=timeout)
    return [thread for thread in threads if thread.is_alive()]
