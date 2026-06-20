""" Test CLI demos """

from __future__ import annotations

import pytest

from cachelab.cli.main import main

# Fast, deterministic demos covering each subsystem; the slower thread/sleep
# demos (sharding, ttl-active) are exercised via the library tests instead.
_DEMOS = [
    "ttl-lazy",
    "worker-queue",
    "backpressure",
    "single-flight",
    "write-through-vs-write-back",
    "write-back-retry",
    "unsafe-race",
    "unsafe-single-flight",
    "unsafe-write-back-resurrection",
    "wall-clock-ttl-bug",
]


@pytest.mark.parametrize("name", _DEMOS)
def test_demo_runs_and_reports(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", name]) == 0
    assert capsys.readouterr().out.strip() != ""


def test_demo_all_runs_end_to_end(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "all"]) == 0
    output = capsys.readouterr().out
    assert "policy benchmark" in output
    assert "unsafe-race" in output
