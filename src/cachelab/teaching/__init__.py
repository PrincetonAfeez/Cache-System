""" Teaching utilities for CacheLab """

from __future__ import annotations

from cachelab.teaching.unsafe_cache import unsafe_race_demo
from cachelab.teaching.unsafe_singleflight import unsafe_singleflight_demo
from cachelab.teaching.unsafe_wall_clock_ttl import unsafe_wall_clock_ttl_demo
from cachelab.teaching.unsafe_write_back import unsafe_write_back_resurrection_demo

__all__ = [
    "unsafe_race_demo",
    "unsafe_singleflight_demo",
    "unsafe_wall_clock_ttl_demo",
    "unsafe_write_back_resurrection_demo",
]
