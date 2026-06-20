""" Test CLI basic commands """

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pytest

from cachelab.cli.commands.basic import (
    _load_cache_state,
    _save_cache_state,
    parse_cli_key,
    parse_cli_value,
    run_basic,
)
from cachelab.cli.main import main
from cachelab.core.cache import Cache
from cachelab.core.config import CacheConfig


def test_parse_cli_key_and_value_json() -> None:
    assert parse_cli_key("42", key_json=True) == 42
    assert parse_cli_value("true", value_json=True) is True


def test_parse_cli_key_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="invalid JSON key"):
        parse_cli_key("{bad", key_json=True)


def test_parse_cli_value_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="invalid JSON value"):
        parse_cli_value("{bad", value_json=True)


def test_run_basic_delete_contains_inspect_dump_clear(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    args_base = ["--state", str(state)]
    assert main(args_base + ["put", "a", "one"]) == 0
    assert main(args_base + ["contains", "a"]) == 0
    assert "yes" in capsys.readouterr().out
    assert main(args_base + ["inspect", "a"]) == 0
    assert "hit_count" in capsys.readouterr().out
    assert main(args_base + ["dump", "--limit", "10"]) == 0
    assert "one" in capsys.readouterr().out
    assert main(args_base + ["delete", "a"]) == 0
    assert "deleted" in capsys.readouterr().out
    assert main(args_base + ["put", "b", "two"]) == 0
    assert main(args_base + ["clear"]) == 0
    assert "cleared" in capsys.readouterr().out


def test_run_basic_put_ttl_and_no_ttl_conflict(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    args = argparse.Namespace(
        state=str(state),
        command="put",
        key="k",
        value="v",
        ttl=30.0,
        no_ttl=True,
        key_json=False,
        value_json=False,
        config=None,
        capacity=8,
        policy="lru",
        shards=1,
        default_ttl=None,
    )
    with pytest.raises(ValueError, match="cannot use both"):
        run_basic(args)


def test_load_state_warns_on_config_mismatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    cache = Cache(capacity=8, policy="lru", shard_count=1)
    cache.put("k", "v")
    _save_cache_state(state, cache)
    args = argparse.Namespace(
        config=None,
        capacity=4,
        policy="fifo",
        shards=2,
        default_ttl=60.0,
    )
    _load_cache_state(state, args)
    err = capsys.readouterr().err
    assert "config differs" in err
    assert "capacity" in err


def test_load_state_legacy_expires_wall(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "config": {"capacity": 8, "policy": "lru", "shard_count": 1, "default_ttl": None},
                "entries": [{"key": "k", "value": "v", "expires_wall": time.time() + 3600}],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(config=None, capacity=8, policy="lru", shards=1, default_ttl=None)
    cache = _load_cache_state(state, args)
    assert cache.contains("k")
    assert "legacy expires_wall" in capsys.readouterr().err


def test_load_state_skips_expired_ttl_remaining(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "config": {"capacity": 8, "policy": "lru", "shard_count": 1, "default_ttl": None},
                "entries": [{"key": "stale", "value": "v", "ttl_remaining": 0}],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(config=None, capacity=8, policy="lru", shards=1, default_ttl=None)
    cache = _load_cache_state(state, args)
    assert not cache.contains("stale")


def test_load_state_warns_when_entries_exceed_capacity(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    entries = [{"key": f"k{i}", "value": str(i), "ttl_remaining": None} for i in range(6)]
    state.write_text(
        json.dumps(
            {
                "config": {"capacity": 8, "policy": "lru", "shard_count": 1, "default_ttl": None},
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(config=None, capacity=2, policy="lru", shards=1, default_ttl=None)
    _load_cache_state(state, args)
    err = capsys.readouterr().err
    assert "excess entries may be evicted" in err
    assert "entries dropped during reload" in err


def test_load_state_with_config_file_warns_ignored_settings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "cache.toml"
    config.write_text(
        '[cache]\ncapacity = 8\npolicy = "lru"\nshard_count = 1\n'
        'write_mode = "write-back"\nworker_count = 2\n',
        encoding="utf-8",
    )
    args = argparse.Namespace(config=str(config), capacity=8, policy="lru", shards=1, default_ttl=None)
    _load_cache_state(tmp_path / "missing.json", args)
    err = capsys.readouterr().err
    assert "do not start workers" in err


def test_load_state_only_policy_mismatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "config": {"capacity": 8, "policy": "lru", "shard_count": 1, "default_ttl": None},
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(config=None, capacity=8, policy="fifo", shards=1, default_ttl=None)
    _load_cache_state(state, args)
    assert "policy saved='lru' active='fifo'" in capsys.readouterr().err


def test_load_state_legacy_expired_wall_entry_skipped(tmp_path: Path) -> None:
    from cachelab.cli.commands.basic import _load_cache_state

    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "config": {"capacity": 8, "policy": "lru", "shard_count": 1, "default_ttl": None},
                "entries": [{"key": "k", "value": "v", "expires_wall": time.time() - 5}],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(config=None, capacity=8, policy="lru", shards=1, default_ttl=None)
    cache = _load_cache_state(state, args)
    assert cache.size() == 0


def test_load_state_entry_without_ttl_fields(tmp_path: Path) -> None:
    from cachelab.cli.commands.basic import _load_cache_state

    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "config": {"capacity": 8, "policy": "lru", "shard_count": 1, "default_ttl": None},
                "entries": [{"key": "k", "value": "v"}],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(config=None, capacity=8, policy="lru", shards=1, default_ttl=None)
    cache = _load_cache_state(state, args)
    assert cache.get("k") == "v"


def test_warn_flag_mismatch_without_config_file_is_noop(capsys: pytest.CaptureFixture[str]) -> None:
    from cachelab.cli.commands.basic import _warn_flag_mismatch_with_config_file

    args = argparse.Namespace(config=None, capacity=4, policy="lru", shards=1, default_ttl=None)
    _warn_flag_mismatch_with_config_file(args, CacheConfig(capacity=8))
    assert capsys.readouterr().err == ""
