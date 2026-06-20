""" Serialization utilities for CacheLab """

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

# Locks older than this are treated as stale (e.g. after a crash).
_STALE_LOCK_SECONDS = 30.0


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)
    return loaded if isinstance(loaded, dict) else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class StateFileLock:
    """Best-effort exclusive lock for CLI state files across processes."""

    def __init__(self, path: Path, *, timeout: float = 5.0) -> None:
        self._lock_path = path.with_suffix(path.suffix + ".lock")
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "StateFileLock":
        deadline = time.monotonic() + self._timeout
        while True:
            if self._try_acquire():
                return self
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"could not acquire state lock: {self._lock_path}"
                ) from None
            time.sleep(0.05)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _try_acquire(self) -> bool:
        try:
            self._fd = os.open(
                self._lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            payload = f"pid={os.getpid()} time={time.time():.3f}\n"
            os.write(self._fd, payload.encode("utf-8"))
            return True
        except FileExistsError:
            if self._lock_is_stale():
                try:
                    self._lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return False

    def _lock_is_stale(self) -> bool:
        try:
            age = time.time() - self._lock_path.stat().st_mtime
        except OSError:
            return True
        return age >= _STALE_LOCK_SECONDS
