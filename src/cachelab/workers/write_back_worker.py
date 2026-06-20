""" Write back worker utilities for CacheLab """

from __future__ import annotations

from typing import Hashable, Protocol

from cachelab.core.exceptions import ValidationError
from cachelab.workers.messages import FlushWriteBack

__all__ = ["FlushWriteBack", "SourceBackend", "is_stale_write_back", "apply_write_back"]


class SourceBackend(Protocol):
    def put_value(self, key: Hashable, value: object) -> None:
        ...

    def delete_value(self, key: Hashable) -> None:
        ...


def is_stale_write_back(
    version_marks: dict[Hashable, int],
    tombstones: dict[Hashable, int],
    job: FlushWriteBack,
) -> bool:
    """Return ``True`` when ``job`` must not be applied to the source backend.

    A put is stale once a newer write or a tombstone has superseded its version
    (this also implements coalescing: only the newest put survives). A delete is
    stale once a newer write replaced the tombstone it was meant to persist.
    """
    current_version = version_marks.get(job.key, 0)
    tombstone_version = tombstones.get(job.key)
    if job.operation == "put":
        return current_version != job.version or (
            tombstone_version is not None and tombstone_version >= job.version
        )
    if job.operation == "delete":
        return current_version != job.version or tombstone_version != job.version
    return True


def apply_write_back(source_backend: SourceBackend, job: FlushWriteBack) -> None:
    """Apply a non-stale write-back job to the source-of-truth backend."""
    if job.operation == "put":
        source_backend.put_value(job.key, job.value)
    elif job.operation == "delete":
        source_backend.delete_value(job.key)
    else:
        raise ValidationError(f"unknown write-back operation: {job.operation}")
