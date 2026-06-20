""" Commands for the CLI """

from __future__ import annotations

from cachelab.cli.commands.basic import BASIC_COMMANDS, run_basic
from cachelab.cli.commands.benchmark import run_benchmark
from cachelab.cli.commands.demo import run_demo
from cachelab.cli.commands.simulate import run_simulate

__all__ = ["BASIC_COMMANDS", "run_basic", "run_benchmark", "run_demo", "run_simulate"]
