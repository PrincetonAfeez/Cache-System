""" Main entry point for the CLI """

from __future__ import annotations

import argparse
import sys

from cachelab.cli.commands import BASIC_COMMANDS, run_basic, run_benchmark, run_demo, run_simulate
from cachelab.cli.parser import build_parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except Exception as exc:
        print(f"cachelab: error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    if args.command in BASIC_COMMANDS:
        return run_basic(args)
    if args.command == "simulate":
        return run_simulate(args)
    if args.command == "benchmark":
        return run_benchmark(args)
    if args.command == "demo":
        return run_demo(args.name)
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
