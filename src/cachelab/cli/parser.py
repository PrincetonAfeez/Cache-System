""" Parser for the CLI """

from __future__ import annotations

import argparse

from cachelab import __version__


def _add_key_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--key-json",
        action="store_true",
        help="parse the key argument as a JSON literal (e.g. true, 42, \"user:1\")",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cachelab",
        description="Concurrent cache lab CLI",
        epilog="Exit codes: 0 success, 1 runtime error, 2 usage error (invalid arguments).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--capacity", type=int, default=128)
    parser.add_argument("--policy", choices=["lru", "lfu", "fifo"], default="lru")
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument(
        "--default-ttl",
        type=float,
        default=None,
        help="default TTL in seconds for basic commands (omit for no default expiry)",
    )
    parser.add_argument("--state", default=".cachelab_state.json")
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "TOML config file for basic commands; replaces --capacity/--policy/--shards "
            "(those flags are ignored when this is set)"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    put = sub.add_parser("put")
    put.add_argument("key")
    put.add_argument("value")
    put.add_argument("--ttl", type=float)
    put.add_argument(
        "--no-ttl",
        action="store_true",
        help="store without expiry even when a default TTL is configured",
    )
    put.add_argument(
        "--value-json",
        action="store_true",
        help="parse the value argument as a JSON literal (objects, arrays, numbers, null)",
    )
    _add_key_flags(put)

    get = sub.add_parser("get")
    get.add_argument("key")
    _add_key_flags(get)

    delete = sub.add_parser("delete")
    delete.add_argument("key")
    _add_key_flags(delete)

    contains = sub.add_parser("contains")
    contains.add_argument("key")
    _add_key_flags(contains)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("key")
    _add_key_flags(inspect)

    dump = sub.add_parser("dump")
    dump.add_argument("--limit", type=int)

    sub.add_parser("clear")
    sub.add_parser("stats")

    patterns = ["uniform", "zipfian", "hotspot", "sequential", "looping", "mixed"]

    simulate = sub.add_parser("simulate")
    simulate.add_argument("--policy", choices=["lru", "lfu", "fifo"], default="lru")
    simulate.add_argument("--pattern", choices=patterns, default="hotspot")
    simulate.add_argument("--capacity", type=int, default=100)
    simulate.add_argument("--requests", type=int, default=10_000)
    simulate.add_argument("--seed", type=int, default=1)
    simulate.add_argument(
        "--shards", type=int, default=1, help="shard count (default 1 isolates pure policy behavior)"
    )

    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--policies", default="lru,lfu,fifo")
    benchmark.add_argument("--pattern", choices=patterns, default="looping")
    benchmark.add_argument("--capacity", type=int, default=100)
    benchmark.add_argument("--requests", type=int, default=50_000)
    benchmark.add_argument("--seed", type=int, default=1)
    benchmark.add_argument(
        "--shards", type=int, default=1, help="shard count (default 1 isolates pure policy behavior)"
    )

    demo = sub.add_parser("demo")
    demo.add_argument(
        "name",
        choices=[
            "ttl-lazy",
            "ttl-active",
            "single-flight",
            "sharding",
            "worker-queue",
            "backpressure",
            "write-through-vs-write-back",
            "write-back-retry",
            "unsafe-race",
            "unsafe-single-flight",
            "unsafe-write-back-resurrection",
            "wall-clock-ttl-bug",
            "all",
        ],
    )
    return parser
