""" Simulate commands for the CLI """

from __future__ import annotations

import argparse

from cachelab.cli.commands.render import print_simulation
from cachelab.workloads.runner import run_simulation


def run_simulate(args: argparse.Namespace) -> int:
    result = run_simulation(
        policy=args.policy,
        pattern=args.pattern,
        capacity=args.capacity,
        requests=args.requests,
        seed=args.seed,
        shards=args.shards,
    )
    print_simulation([result])
    return 0
