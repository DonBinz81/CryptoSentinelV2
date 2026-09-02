"""Unit tests for the per-position serialisation lock.

Local-runnable: the module under test imports only asyncio and the logger.
"""

from __future__ import annotations

import asyncio

from backend.app.agent.perp_position_lock import PerpPositionLocks


def test_same_position_gets_the_same_lock() -> None:
    locks = PerpPositionLocks()
    assert locks.get("pos_a") is locks.get("pos_a")


def test_different_positions_get_different_locks() -> None:
    """Two positions must never block each other: the guard is per position."""
    locks = PerpPositionLocks()
    assert locks.get("pos_a") is not locks.get("pos_b")


async def test_lock_is_reported_as_held_only_while_owned() -> None:
    locks = PerpPositionLocks()
    assert locks.is_held("pos_a") is False
    async with locks.get("pos_a"):
        assert locks.is_held("pos_a") is True
    assert locks.is_held("pos_a") is False


async def test_two_concurrent_writers_are_serialised() -> None:
    """The double-tap case: two overlapping operations on one position must not
    interleave between their read and their write."""
    locks = PerpPositionLocks()
    size = {"value": 100}
    order: list[str] = []

    async def close_half(tag: str) -> None:
        async with locks.get("pos_a"):
            order.append(f"{tag}:start")
            current = size["value"]
            await asyncio.sleep(0)  # the interleaving point a venue call creates
            size["value"] = current - current // 2
            order.append(f"{tag}:end")

    await asyncio.gather(close_half("first"), close_half("second"))

    # Serialised: no "start" appears between another pair's start and end.
    assert order in (
        ["first:start", "first:end", "second:start", "second:end"],
        ["second:start", "second:end", "first:start", "first:end"],
    )
    # 100 -> 50 -> 25. Without the lock both would read 100 and write 50.
    assert size["value"] == 25


async def test_operations_on_distinct_positions_run_concurrently() -> None:
    locks = PerpPositionLocks()
    started = asyncio.Event()

    async def hold(position_id: str) -> None:
        async with locks.get(position_id):
            started.set()
            await asyncio.sleep(0.05)

    async def other() -> None:
        await started.wait()
        async with locks.get("pos_b"):  # must not wait for pos_a
            pass

    await asyncio.wait_for(asyncio.gather(hold("pos_a"), other()), timeout=1.0)


async def test_assert_held_never_raises() -> None:
    """A missing lock is logged, not raised: refusing to close a position would
    be worse than closing it unserialised."""
    locks = PerpPositionLocks()
    locks.assert_held("pos_a", caller="test")  # not held: logs, returns
    async with locks.get("pos_a"):
        locks.assert_held("pos_a", caller="test")


async def test_discard_frees_an_idle_lock_but_never_a_held_one() -> None:
    locks = PerpPositionLocks()
    async with locks.get("pos_a"):
        locks.discard("pos_a")
        assert locks.tracked() == 1  # still owned: must survive
    locks.discard("pos_a")
    assert locks.tracked() == 0


def test_discard_of_an_unknown_position_is_a_no_op() -> None:
    locks = PerpPositionLocks()
    locks.discard("never_seen")
    assert locks.tracked() == 0
