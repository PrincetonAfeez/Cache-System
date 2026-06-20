""" Basic commands for the CLI """

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, cast

from cachelab.cli.commands.render import fmt_float, stats_table
from cachelab.core.cache import Cache
from cachelab.core.config import CacheConfig
from cachelab.observability.tables import format_table
from cachelab.storage.serialization import StateFileLock, read_json, write_json
from cachelab.storage.write_modes import WriteMode

BASIC_COMMANDS = frozenset(
    {"put", "get", "delete", "contains", "inspect", "dump", "clear", "stats"}
)

_CLI_MISS = object()
_LEGACY_WALL_CLOCK_WARNED = False


def run_basic(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    with StateFileLock(state_path):
        cache = _load_cache_state(state_path, args)
        key: Any = None
        if hasattr(args, "key"):
            key = parse_cli_key(args.key, key_json=getattr(args, "key_json", False))
        if args.command == "put":
            if args.no_ttl and args.ttl is not None:
                raise ValueError("cannot use both --ttl and --no-ttl")
            value = parse_cli_value(args.value, value_json=getattr(args, "value_json", False))
            if args.no_ttl:
                cache.put(key, value, ttl=None)
            elif args.ttl is not None:
                cache.put(key, value, ttl=args.ttl)
            else:
                cache.put(key, value)
            _save_cache_state(state_path, cache)
            print(f"stored {args.key}")
        elif args.command == "get":
            value = cache.get(key, _CLI_MISS)
            if value is _CLI_MISS:
                print("(miss)")
            else:
                print(value)
        elif args.command == "delete":
            deleted = cache.delete(key)
            _save_cache_state(state_path, cache)
            print("deleted" if deleted else "not found")
        elif args.command == "contains":
            print("yes" if cache.contains(key) else "no")
        elif args.command == "inspect":
            snapshot = cache.inspect(key)
            if snapshot is None:
                print("not found")
            else:
                print(
                    format_table(
                        ["field", "value"],
                        [
                            ["key", snapshot.key],
                            ["value", snapshot.value],
                            ["hit_count", snapshot.hit_count],
                            ["ttl_remaining", fmt_float(snapshot.ttl_remaining)],
                            ["version", snapshot.version],
                            ["dirty", snapshot.dirty],
                        ],
                    )
                )
        elif args.command == "dump":
            rows = [
                [snap.key, snap.value, snap.version, fmt_float(snap.ttl_remaining), snap.hit_count]
                for snap in cache.dump(limit=args.limit)
            ]
            print(
                format_table(
                    ["key", "value", "version", "ttl", "hits"],
                    rows or [["-", "-", "-", "-", "-"]],
                )
            )
        elif args.command == "clear":
            cache.clear()
            _save_cache_state(state_path, cache)
            print("cleared")
        elif args.command == "stats":
            # Note: the CLI is stateless across invocations, so this command rebuilds
            # the cache from disk; counters reflect this process only, not historical
            # traffic. Use `simulate`/`benchmark` for meaningful hit-ratio numbers.
            print(stats_table(cache))
    return 0


def parse_cli_key(raw: str, *, key_json: bool) -> Any:
    if not key_json:
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON key: {raw!r}") from exc


def parse_cli_value(raw: str, *, value_json: bool) -> Any:
    if not value_json:
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON value: {raw!r}") from exc


def _warn_ignored_config_settings(config: CacheConfig) -> None:
    if config.worker_count <= 0 and config.write_mode == WriteMode.CACHE_ONLY.value:
        return
    print(
        "cachelab: note: basic CLI commands do not start workers or a source backend; "
        "settings such as worker_count, write_mode, and active_expiration apply only "
        "to the library API.",
        file=sys.stderr,
    )


def _config_from_args(args: argparse.Namespace) -> CacheConfig:
    if getattr(args, "config", None):
        return CacheConfig.from_file(args.config)
    default_ttl = getattr(args, "default_ttl", None)
    return CacheConfig(
        capacity=args.capacity,
        policy=args.policy,
        shard_count=args.shards,
        default_ttl=default_ttl,
    )


def _warn_flag_mismatch_with_config_file(args: argparse.Namespace, config: CacheConfig) -> None:
    if not getattr(args, "config", None):
        return
    mismatches: list[str] = []
    if args.capacity != config.capacity:
        mismatches.append(f"--capacity={args.capacity} (file has {config.capacity})")
    if args.policy != config.policy:
        mismatches.append(f"--policy={args.policy} (file has {config.policy})")
    if args.shards != config.shard_count:
        mismatches.append(f"--shards={args.shards} (file has {config.shard_count})")
    if getattr(args, "default_ttl", None) != config.default_ttl:
        mismatches.append(
            f"--default-ttl={getattr(args, 'default_ttl', None)!r} "
            f"(file has {config.default_ttl!r})"
        )
    if mismatches:
        joined = "; ".join(mismatches)
        print(
            f"cachelab: note: --config replaces sizing flags; ignored: {joined}",
            file=sys.stderr,
        )


def _load_cache_state(path: Path, args: argparse.Namespace) -> Cache:
    config = _config_from_args(args)
    if getattr(args, "config", None):
        _warn_flag_mismatch_with_config_file(args, config)
        _warn_ignored_config_settings(config)
        cache = Cache(config=config)
    else:
        cache = Cache(config=config)
    state = read_json(path)
    saved_config = state.get("config")
    if isinstance(saved_config, dict):
        _warn_saved_config_mismatch(saved_config, config)
    wall_now = time.time()
    items = [
        item
        for item in state.get("entries", [])
        if isinstance(item, dict) and "key" in item
    ]
    if len(items) > config.capacity:
        print(
            f"cachelab: warning: state has {len(items)} entries but capacity is "
            f"{config.capacity}; excess entries may be evicted during reload",
            file=sys.stderr,
        )
    for item in items:
        ttl = _ttl_from_state_item(item, wall_now=wall_now)
        if ttl is _SKIP_ENTRY:
            continue
        cache.put(item["key"], item.get("value"), ttl=cast(float | None, ttl))
        hit_count = item.get("hit_count")
        if isinstance(hit_count, int) and hit_count > 0:
            cache.restore_entry_metadata(item["key"], hit_count=hit_count)
    dropped = len(items) - cache.size()
    if dropped > 0:
        print(
            f"cachelab: warning: {dropped} entries dropped during reload "
            f"(capacity={config.capacity})",
            file=sys.stderr,
        )
    return cache


def _warn_saved_config_mismatch(saved: dict[str, Any], active: CacheConfig) -> None:
    fields = (
        ("capacity", active.capacity),
        ("policy", active.policy),
        ("shard_count", active.shard_count),
        ("default_ttl", active.default_ttl),
    )
    mismatches = [
        f"{name} saved={saved.get(name)!r} active={expected!r}"
        for name, expected in fields
        if name in saved and saved.get(name) != expected
    ]
    if mismatches:
        print(
            "cachelab: warning: state file config differs from active settings: "
            + "; ".join(mismatches),
            file=sys.stderr,
        )


_SKIP_ENTRY = object()


def _ttl_from_state_item(item: dict[str, Any], *, wall_now: float) -> float | None | object:
    global _LEGACY_WALL_CLOCK_WARNED
    if "ttl_remaining" in item:
        raw = item.get("ttl_remaining")
        if raw is None:
            return None
        try:
            remaining = float(raw)
        except (TypeError, ValueError):
            return _SKIP_ENTRY
        if remaining <= 0:
            return _SKIP_ENTRY
        return remaining
    expires_wall = item.get("expires_wall")
    if expires_wall is not None:
        if not _LEGACY_WALL_CLOCK_WARNED:
            print(
                "cachelab: note: loading legacy expires_wall timestamps uses wall clock; "
                "re-save the state file to migrate to ttl_remaining",
                file=sys.stderr,
            )
            _LEGACY_WALL_CLOCK_WARNED = True
        try:
            remaining = float(expires_wall) - wall_now
        except (TypeError, ValueError):
            return _SKIP_ENTRY
        if remaining <= 0:
            return _SKIP_ENTRY
        return remaining
    return None


def _save_cache_state(path: Path, cache: Cache) -> None:
    entries: list[dict[str, Any]] = []
    for snapshot in cache.dump():
        entries.append(
            {
                "key": snapshot.key,
                "value": snapshot.value,
                "ttl_remaining": snapshot.ttl_remaining,
                "hit_count": snapshot.hit_count,
            }
        )
    write_json(
        path,
        {
            "config": {
                "capacity": cache.config.capacity,
                "policy": cache.config.policy,
                "shard_count": cache.config.shard_count,
                "default_ttl": cache.config.default_ttl,
            },
            "entries": entries,
        },
    )
