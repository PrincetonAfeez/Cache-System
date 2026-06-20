""" Test config comprehensive """

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cachelab.core.config import CacheConfig, _load_toml, _normalize_config
from cachelab.core.exceptions import ConfigurationError


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"shard_count": 0}, "shard_count"),
        ({"default_ttl": -1}, "default_ttl"),
        ({"worker_count": -1}, "worker_count"),
        ({"queue_size": -1}, "queue_size"),
        ({"scheduler_interval": -1}, "scheduler_interval"),
        ({"write_back_retry_count": -1}, "write_back_retry_count"),
        ({"backend": "redis"}, "unsupported backend"),
    ],
)
def test_config_validation_errors(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        CacheConfig(**kwargs)


def test_config_from_file_supports_aliases(tmp_path: Path) -> None:
    path = tmp_path / "cache.toml"
    path.write_text(
        """
[cache]
capacity = 16
policy = "fifo"
shards = 2
workers = 1
default_ttl_seconds = 30
queue_maxsize = 4
retry_count = 1
retry_delay = 0.05
""",
        encoding="utf-8",
    )
    config = CacheConfig.from_file(path)
    assert config.shard_count == 2
    assert config.worker_count == 1
    assert config.default_ttl == 30
    assert config.queue_size == 4
    assert config.write_back_retry_count == 1
    assert config.write_back_retry_delay == 0.05


def test_config_from_file_uses_root_table(tmp_path: Path) -> None:
    path = tmp_path / "flat.toml"
    path.write_text('capacity = 12\npolicy = "lru"\nshard_count = 1\n', encoding="utf-8")
    config = CacheConfig.from_file(path)
    assert config.capacity == 12


def test_load_toml_rejects_non_dict_root(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_bytes(b"[cache]\ncapacity = 1\n")
    with patch("tomllib.load", return_value=[]):
        with pytest.raises(ConfigurationError, match="did not contain a TOML table"):
            _load_toml(path)


def test_normalize_config_maps_default_ttl_alias() -> None:
    normalized = _normalize_config({"default TTL": 15})
    assert normalized["default_ttl"] == 15


def test_cache_constructor_rejects_conflicting_config_and_kwargs() -> None:
    config = CacheConfig(capacity=8)
    with pytest.raises(ConfigurationError, match="do not also pass"):
        from cachelab import Cache

        Cache(config=config, capacity=16)
