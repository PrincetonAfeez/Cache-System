""" Test TTL """

from __future__ import annotations

import pytest

from cachelab import Cache, FakeClock
from cachelab.core.exceptions import ValidationError


def test_default_ttl_expires_lazily_with_fake_clock() -> None:
    clock = FakeClock()
    cache = Cache(capacity=2, default_ttl=5, clock=clock)
    cache.put("a", 1)
    clock.advance(4.9)
    assert cache.get("a") == 1
    clock.advance(0.2)
    assert cache.get("a") is None
    stats = cache.stats()
    assert stats.expirations == 1
    assert stats.misses >= 1


def test_explicit_none_ttl_disables_default_ttl() -> None:
    clock = FakeClock()
    cache = Cache(capacity=2, default_ttl=1, clock=clock)
    cache.put("forever", 1, ttl=None)
    clock.advance(100)
    assert cache.get("forever") == 1


def test_per_key_ttl_overrides_default() -> None:
    clock = FakeClock()
    cache = Cache(capacity=2, default_ttl=100, clock=clock)
    cache.put("short", 1, ttl=2)
    clock.advance(3)
    assert cache.contains("short") is False


def test_non_positive_ttl_is_rejected() -> None:
    cache = Cache(capacity=4)
    with pytest.raises(ValidationError):
        cache.put("a", 1, ttl=0)
    with pytest.raises(ValidationError):
        cache.put("a", 1, ttl=-5)
    assert cache.get("a") is None  # nothing was stored


def test_get_or_compute_validates_ttl_before_running_loader() -> None:
    cache = Cache(capacity=4)
    ran: list[int] = []

    def loader() -> str:
        ran.append(1)
        return "v"

    with pytest.raises(ValidationError):
        cache.get_or_compute("k", loader, ttl=-1)
    assert ran == []  # ttl rejected before any side effect


def test_update_without_ttl_preserves_original_expiry() -> None:
    # Re-putting a key without an explicit ttl keeps its original absolute
    # expiry (and created_at): an update changes the value, not the lifetime.
    clock = FakeClock()
    cache = Cache(capacity=2, clock=clock)
    cache.put("a", 1, ttl=10)
    created = cache.inspect("a").created_at  # type: ignore[union-attr]
    clock.advance(5)
    cache.put("a", 2)
    snapshot = cache.inspect("a")
    assert snapshot is not None
    assert snapshot.value == 2
    assert snapshot.created_at == created
    assert snapshot.expires_at == 10
    clock.advance(5.0)
    assert cache.get("a") is None
