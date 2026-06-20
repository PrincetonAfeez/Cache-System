""" Configuration utilities for CacheLab """

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cachelab.core.exceptions import ConfigurationError
from cachelab.storage.write_modes import WriteMode

_SUPPORTED_BACKENDS = frozenset({"memory"})
_SUPPORTED_POLICIES = frozenset({"lru", "lfu", "fifo"})
_SUPPORTED_WRITE_MODES = frozenset(mode.value for mode in WriteMode)


@dataclass(frozen=True, slots=True)
class CacheConfig:
    capacity: int = 128
    default_ttl: float | None = None
    policy: str = "lru"
    shard_count: int = 1
    worker_count: int = 0
    backend: str = "memory"
    write_mode: str = WriteMode.CACHE_ONLY.value
    scheduler_interval: float = 1.0
    queue_size: int = 0
    write_back_retry_count: int = 2
    write_back_retry_delay: float = 0.01
    shutdown_flush: bool = True
    shutdown_timeout: float = 5.0
    active_expiration: bool = True
    queue_put_timeout: float = 1.0

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ConfigurationError("capacity must be >= 1")
        if self.shard_count <= 0:
            raise ConfigurationError("shard_count must be > 0")
        if self.capacity < self.shard_count:
            raise ConfigurationError(
                f"capacity ({self.capacity}) must be >= shard_count ({self.shard_count}) "
                "so every shard can hold at least one entry"
            )
        if self.default_ttl is not None and self.default_ttl < 0:
            raise ConfigurationError("default_ttl must be >= 0 (0 or None disables expiry)")
        if self.worker_count < 0:
            raise ConfigurationError("worker_count must be >= 0")
        if self.queue_size < 0:
            raise ConfigurationError("queue_size must be >= 0")
        if self.scheduler_interval < 0:
            raise ConfigurationError("scheduler_interval must be >= 0")
        if self.active_expiration and self.scheduler_interval <= 0:
            raise ConfigurationError(
                "scheduler_interval must be > 0 when active_expiration is enabled"
            )
        if self.write_back_retry_count < 0:
            raise ConfigurationError("write_back_retry_count must be >= 0")
        if self.policy.lower() not in _SUPPORTED_POLICIES:
            supported = ", ".join(sorted(_SUPPORTED_POLICIES))
            raise ConfigurationError(
                f"unsupported policy {self.policy!r}; supported policies: {supported}"
            )
        if self.write_mode not in _SUPPORTED_WRITE_MODES:
            supported = ", ".join(sorted(_SUPPORTED_WRITE_MODES))
            raise ConfigurationError(
                f"unsupported write_mode {self.write_mode!r}; supported write modes: {supported}"
            )
        if self.backend not in _SUPPORTED_BACKENDS:
            supported = ", ".join(sorted(_SUPPORTED_BACKENDS))
            raise ConfigurationError(
                f"unsupported backend {self.backend!r}; supported backends: {supported}"
            )

    @classmethod
    def from_file(cls, path: str | Path) -> "CacheConfig":
        path = Path(path)
        data = _load_toml(path)
        cache_data = data.get("cache", data)
        return cls(**_normalize_config(cache_data))


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError as exc:  # pragma: no cover - Python 3.11+ has tomllib.
        raise ConfigurationError("tomllib is required to read TOML configs") from exc

    with path.open("rb") as file:
        loaded = tomllib.load(file)
    if not isinstance(loaded, dict):
        raise ConfigurationError(f"{path} did not contain a TOML table")
    return loaded


def _normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "default TTL": "default_ttl",
        "default_ttl_seconds": "default_ttl",
        "shards": "shard_count",
        "workers": "worker_count",
        "queue_maxsize": "queue_size",
        "retry_count": "write_back_retry_count",
        "retry_delay": "write_back_retry_delay",
    }
    normalized: dict[str, Any] = {}
    unknown: list[str] = []
    valid = set(CacheConfig.__dataclass_fields__)
    for key, value in data.items():
        field = aliases.get(key, key)
        if field in valid:
            normalized[field] = value
        else:
            unknown.append(key)
    if unknown:
        raise ConfigurationError(
            f"unknown config key(s): {', '.join(sorted(unknown))}; "
            f"valid keys: {', '.join(sorted(valid))}"
        )
    return normalized
