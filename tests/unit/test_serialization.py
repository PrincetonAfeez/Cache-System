""" Test serialization """

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cachelab.storage.serialization import StateFileLock, read_json, write_json


def test_read_json_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    assert read_json(tmp_path / "missing.json") == {}


def test_read_json_non_dict_payload_returns_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert read_json(path) == {}


def test_write_json_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    payload = {"config": {"capacity": 4}, "entries": []}
    write_json(path, payload)
    assert read_json(path) == payload


def test_write_json_cleanup_unlink_oserror(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    with patch("cachelab.storage.serialization.json.dump", side_effect=OSError("disk full")):
        with patch("cachelab.storage.serialization.os.unlink", side_effect=OSError("busy")):
            with pytest.raises(OSError, match="disk full"):
                write_json(path, {"entries": []})


def test_state_file_lock_try_acquire_stale_unlink_oserror(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    lock_path = state.with_suffix(state.suffix + ".lock")
    lock_path.write_text("stale", encoding="utf-8")
    stale_time = time.time() - 60.0
    os.utime(lock_path, (stale_time, stale_time))
    lock = StateFileLock(state)
    with patch.object(Path, "unlink", side_effect=OSError("busy")):
        assert lock._try_acquire() is False


def test_state_file_lock_stale_check_when_stat_fails(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    lock = StateFileLock(state)
    with patch.object(Path, "stat", side_effect=OSError("missing")):
        assert lock._lock_is_stale() is True


def test_state_file_lock_acquire_and_release(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    with StateFileLock(state):
        lock_path = state.with_suffix(state.suffix + ".lock")
        assert lock_path.exists()
    assert not lock_path.exists()


def test_state_file_lock_timeout_when_held(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    lock_path = state.with_suffix(state.suffix + ".lock")
    lock_path.write_text("held", encoding="utf-8")
    with pytest.raises(TimeoutError, match="could not acquire state lock"):
        with StateFileLock(state, timeout=0.1):
            pass


def test_state_file_lock_stale_lock_is_replaced(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    lock_path = state.with_suffix(state.suffix + ".lock")
    lock_path.write_text("stale", encoding="utf-8")
    stale_time = time.time() - 60.0
    os.utime(lock_path, (stale_time, stale_time))
    with StateFileLock(state, timeout=1.0):
        assert lock_path.exists()


def test_state_file_lock_exit_ignores_unlink_oserror(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    lock = StateFileLock(state)
    lock.__enter__()
    with patch.object(Path, "unlink", side_effect=OSError("busy")):
        lock.__exit__(None, None, None)
