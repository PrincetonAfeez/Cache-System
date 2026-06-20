""" Test config """

from __future__ import annotations

from pathlib import Path

import pytest

from cachelab.core.config import CacheConfig
from cachelab.core.exceptions import ConfigurationError


def test_config_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "cache.toml"
    path.write_text(
        """
[cache]
capacity = 10
policy = "lfu"
shard_count = 2
worker_count = 1
""",
        encoding="utf-8",
    )
    config = CacheConfig.from_file(path)
    assert config.capacity == 10
    assert config.policy == "lfu"
    assert config.shard_count == 2
    assert config.worker_count == 1


def test_unknown_config_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("[cache]\ncapacuty = 10\n", encoding="utf-8")  # typo
    with pytest.raises(ConfigurationError):
        CacheConfig.from_file(path)


def test_capacity_zero_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        CacheConfig(capacity=0)


def test_capacity_below_shard_count_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        CacheConfig(capacity=2, shard_count=8)


def test_unsupported_policy_is_rejected_at_config_time() -> None:
    with pytest.raises(ConfigurationError):
        CacheConfig(policy="bogus")


def test_unsupported_write_mode_is_rejected_at_config_time() -> None:
    with pytest.raises(ConfigurationError):
        CacheConfig(write_mode="bogus")


def test_active_expiration_with_zero_interval_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="scheduler_interval"):
        CacheConfig(active_expiration=True, scheduler_interval=0)
