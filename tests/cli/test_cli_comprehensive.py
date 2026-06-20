""" Test CLI comprehensive """

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cachelab.cli.commands.basic import run_basic
from cachelab.cli.commands.demo import run_demo
from cachelab.cli.main import _dispatch, main


def test_main_runtime_error_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("cachelab.cli.main._dispatch", side_effect=RuntimeError("boom")):
        assert main(["stats"]) == 1
    assert "cachelab: error: boom" in capsys.readouterr().err


def test_dispatch_unknown_command_raises() -> None:
    args = argparse.Namespace(command="bogus")
    with pytest.raises(ValueError, match="unknown command"):
        _dispatch(args)


def test_run_demo_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="unknown demo"):
        run_demo("not-a-demo")


def test_run_benchmark_command(capsys: pytest.CaptureFixture[str]) -> None:
    from cachelab.cli.commands.benchmark import run_benchmark

    args = argparse.Namespace(
        policies="lru,fifo",
        pattern="sequential",
        capacity=10,
        requests=100,
        seed=1,
        shards=1,
    )
    assert run_benchmark(args) == 0
    out = capsys.readouterr().out
    assert "lru" in out
    assert "fifo" in out


def test_cli_benchmark_via_main(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["benchmark", "--policies", "fifo", "--pattern", "sequential", "--requests", "20"]) == 0
    assert "fifo" in capsys.readouterr().out


def test_cli_simulate_via_main(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["simulate", "--policy", "lru", "--pattern", "looping", "--requests", "50"]) == 0
    assert "lru" in capsys.readouterr().out


def test_cli_demo_unknown_name_exits_two() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["demo", "not-a-demo"])
    assert exc.value.code == 2


def test_cli_sharding_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "sharding"]) == 0
    assert capsys.readouterr().out.strip()


def test_cli_ttl_active_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "ttl-active"]) == 0
    assert capsys.readouterr().out.strip()


def test_run_basic_put_with_ttl(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    args = argparse.Namespace(
        state=str(state),
        command="put",
        key="k",
        value="v",
        ttl=30.0,
        no_ttl=False,
        key_json=False,
        value_json=False,
        config=None,
        capacity=8,
        policy="lru",
        shards=1,
        default_ttl=None,
    )
    assert run_basic(args) == 0
    assert "stored" in capsys.readouterr().out


def test_run_basic_inspect_missing_key(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    args = argparse.Namespace(
        state=str(state),
        command="inspect",
        key="missing",
        config=None,
        capacity=8,
        policy="lru",
        shards=1,
        default_ttl=None,
    )
    assert run_basic(args) == 0
    assert "not found" in capsys.readouterr().out


def test_config_flag_mismatch_warnings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "cache.toml"
    config.write_text('[cache]\ncapacity = 8\npolicy = "lru"\nshard_count = 1\n', encoding="utf-8")
    state = tmp_path / "state.json"
    assert (
        main(
            [
                "--state",
                str(state),
                "--config",
                str(config),
                "--capacity",
                "4",
                "--policy",
                "fifo",
                "--shards",
                "2",
                "--default-ttl",
                "10",
                "stats",
            ]
        )
        == 0
    )
    err = capsys.readouterr().err
    assert "--capacity=4" in err
    assert "--policy=fifo" in err
    assert "--shards=2" in err
    assert "--default-ttl=10" in err


def test_load_state_invalid_ttl_and_legacy_fields(tmp_path: Path) -> None:
    from cachelab.cli.commands.basic import _load_cache_state

    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "config": {"capacity": 8, "policy": "lru", "shard_count": 1, "default_ttl": None},
                "entries": [
                    {"key": "bad-ttl", "value": "v", "ttl_remaining": "nope"},
                    {"key": "expired-wall", "value": "v", "expires_wall": time.time() - 10},
                    {"key": "bad-wall", "value": "v", "expires_wall": "bad"},
                ],
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(config=None, capacity=8, policy="lru", shards=1, default_ttl=None)
    cache = _load_cache_state(state, args)
    assert cache.size() == 0


def test_main_module_entry_point() -> None:
    from cachelab.cli import main as cli_main

    with patch.object(sys, "argv", ["cachelab", "--version"]):
        with pytest.raises(SystemExit) as exc:
            cli_main.main()
        assert exc.value.code == 0
