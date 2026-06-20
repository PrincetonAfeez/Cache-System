""" Hashing utilities for CacheLab """

from __future__ import annotations

import hashlib
from typing import Hashable


def _canonical(key: Hashable) -> tuple[str, object]:
    """Collapse keys that are equal under ``==`` but render differently.

    Python's data model guarantees ``a == b`` implies ``hash(a) == hash(b)``,
    yet ``repr`` does not respect numeric equality: ``repr(1)``, ``repr(1.0)``
    and ``repr(True)`` all differ even though the three keys share one dict
    slot. Hashing ``repr`` directly would therefore route equal keys to
    different shards and make them miss each other.

    We canonicalize the numeric tower (bool/int/integral float) to a single
    tagged form so equal keys hash identically, while keeping the result stable
    across processes (no dependency on the randomized ``hash`` seed). Exotic
    equal-but-distinct types (e.g. ``1.5 == Fraction(3, 2)``) remain a
    documented edge case.
    """
    if isinstance(key, bool):
        return ("int", int(key))
    if isinstance(key, int):
        return ("int", key)
    if isinstance(key, float) and key.is_integer():
        return ("int", int(key))
    return ("repr", repr(key))


def stable_hash(key: Hashable) -> int:
    encoded = repr(_canonical(key)).encode("utf-8", errors="backslashreplace")
    digest = hashlib.blake2b(encoded, digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=False)
