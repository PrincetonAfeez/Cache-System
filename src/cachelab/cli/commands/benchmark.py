""" Benchmark commands for the CLI """

from __future__ import annotations

import argparse

from cachelab.cli.commands.render import print_simulation
from cachelab.workloads.benchmark import benchmark_policies


def run_benchmark(args: argparse.Namespace) -> int:
    policies = [policy.strip() for policy in args.policies.split(",") if policy.strip()]
    rows = benchmark_policies(
        policies=policies,
        pattern=args.pattern,
        capacity=args.capacity,
        requests=args.requests,
        seed=args.seed,
        shards=args.shards,
    )
    print_simulation(rows)
    return 0
