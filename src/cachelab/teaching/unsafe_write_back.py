""" Unsafe write back utilities for CacheLab """

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Hashable


@dataclass(frozen=True, slots=True)
class UnsafeWrite:
    key: Hashable
    value: Any
    operation: str


def unsafe_write_back_resurrection_demo() -> dict[str, Any]:
    """Deterministically illustrate the write-back resurrection hazard.

    A real system hits this through a concurrency race: a slow pending ``put``
    flush lands after a later ``delete``. We reproduce the *outcome*
    deterministically (no versions/tombstones, jobs applied newest-first) so the
    teaching test is reliable. The real cache prevents it with per-key versions
    and delete tombstones; see ``cachelab.workers.write_back_worker``.
    """
    source: dict[Hashable, Any] = {}
    queue: deque[UnsafeWrite] = deque()
    queue.append(UnsafeWrite("user:1", "old-value", "put"))
    queue.append(UnsafeWrite("user:1", None, "delete"))
    # Apply jobs out of order (delete first, then the stale put) exactly as a
    # late-arriving pending put would: the unsafe backend has no version guard.
    delete = queue.pop()
    if delete.operation == "delete":
        source.pop(delete.key, None)
    stale_put = queue.pop()
    if stale_put.operation == "put":
        source[stale_put.key] = stale_put.value
    return {"source": dict(source), "resurrected": source.get("user:1") == "old-value"}
