""" Test CLI smoke """

from __future__ import annotations

from pathlib import Path

import pytest

import cachelab
from cachelab import Cache
from cachelab.cli.main import main


def test_package_exposes_version() -> None:
    assert isinstance(cachelab.__version__, str)
    assert cachelab.__version__


def test_cli_version_flag_prints_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "cachelab" in capsys.readouterr().out


def test_cli_usage_error_exits_two() -> None:
    # An invalid pattern is rejected by argparse (choices) -> usage error, exit 2.
    with pytest.raises(SystemExit) as exc:
        main(["simulate", "--pattern", "bogus"])
    assert exc.value.code == 2


def test_cli_put_get_stats_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    assert main(["--state", str(state), "put", "a", "one"]) == 0
    assert main(["--state", str(state), "get", "a"]) == 0
    captured = capsys.readouterr()
    assert "one" in captured.out
    assert main(["--state", str(state), "stats"]) == 0
    captured = capsys.readouterr()
    assert "hit_ratio" in captured.out


def test_cli_get_distinguishes_cached_none_from_miss(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state.json"
    from cachelab.cli.commands.basic import _save_cache_state

    cache = Cache(capacity=4)
    cache.put("nil", None)
    _save_cache_state(state, cache)
    assert main(["--state", str(state), "get", "nil"]) == 0
    assert capsys.readouterr().out.strip() == "None"
    assert main(["--state", str(state), "get", "missing"]) == 0
    assert capsys.readouterr().out.strip() == "(miss)"


def test_cli_put_no_ttl_overrides_default(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    config = tmp_path / "cache.toml"
    config.write_text(
        "[cache]\ncapacity = 8\ndefault_ttl = 30\npolicy = \"lru\"\nshard_count = 1\n",
        encoding="utf-8",
    )
    assert main(["--state", str(state), "--config", str(config), "put", "k", "v", "--no-ttl"]) == 0
    import argparse

    from cachelab.cli.commands.basic import _load_cache_state

    args = argparse.Namespace(config=str(config), capacity=8, policy="lru", shards=1, default_ttl=None)
    cache = _load_cache_state(state, args)
    inspected = cache.inspect("k")
    assert inspected is not None
    assert inspected.ttl is None


def test_cli_simulate_and_demo_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["simulate", "--policy", "fifo", "--pattern", "uniform", "--requests", "50"]) == 0
    assert "fifo" in capsys.readouterr().out
    assert main(["demo", "ttl-lazy"]) == 0
    assert "lazy get after ttl" in capsys.readouterr().out
