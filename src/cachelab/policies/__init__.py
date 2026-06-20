""" Policy utilities for CacheLab """

from __future__ import annotations

from cachelab.policies.base import EvictionPolicy, make_policy
from cachelab.policies.fifo import FIFOPolicy
from cachelab.policies.lfu import LFUPolicy
from cachelab.policies.lru import LRUPolicy

__all__ = ["EvictionPolicy", "FIFOPolicy", "LFUPolicy", "LRUPolicy", "make_policy"]
