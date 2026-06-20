""" Test unsafe examples fail """

from __future__ import annotations

from cachelab.teaching import (
    unsafe_race_demo,
    unsafe_singleflight_demo,
    unsafe_wall_clock_ttl_demo,
    unsafe_write_back_resurrection_demo,
)


def test_unsafe_race_overflows_capacity() -> None:
    # The unsafe cache's bug is a data race, so it is inherently probabilistic;
    # assert it surfaces in at least one of several trials rather than relying on
    # a single scheduling outcome.
    overflowed = any(
        unsafe_race_demo(threads=20, capacity=1)["final_size"] > 1 for _ in range(5)
    )
    assert overflowed


def test_unsafe_singleflight_duplicates_loader_work() -> None:
    duplicated = any(
        unsafe_singleflight_demo(threads=20)["loader_calls"] > 1 for _ in range(5)
    )
    assert duplicated


def test_unsafe_write_back_resurrects_deleted_value() -> None:
    result = unsafe_write_back_resurrection_demo()
    assert result["resurrected"] is True


def test_unsafe_wall_clock_can_make_expired_entry_alive_again() -> None:
    result = unsafe_wall_clock_ttl_demo()
    assert result["expired_after_forward"] is True
    assert result["incorrectly_alive_after_backward_jump"] is True
