"""Serialisation of everything that mutates a single perp position.

Why this exists
---------------
Position management (fast tick: ratchet, Smart SL, TP/SL exits) and the manual
close endpoint run in the SAME event loop but with SEPARATE database sessions:
the loops are ``asyncio.create_task`` started in the app lifespan, while an HTTP
request gets its own session. Every ``await`` inside position handling -- a
venue call, a database round trip -- is a point where the other side can
interleave, read the same row into its own session, and compute
``size - closed`` from a value that is already stale. Both writes then land and
the last commit wins: two close trades are recorded, one reduction is lost.

The rule
--------
One owner per position, held by the OUTERMOST caller:

* the fast tick takes it around the whole handling of one position, so ratchet,
  Smart SL and exits all run under a single acquisition;
* the manual close endpoint takes it around read-check-execute-persist;
* ``close_all_and_pause`` takes it per position.

Inner helpers (``_close_perp_position`` and the Smart SL branch) never acquire
it: ``asyncio.Lock`` is not reentrant, and a nested acquisition would deadlock
the loop rather than protect anything. ``assert_held`` exists to make that
contract observable at runtime instead of relying on review.

Scope and limits (deliberate, documented per the live-readiness review)
----------------------------------------------------------------------
* This protects a SINGLE process. It does not protect across workers,
  processes or hosts: an in-memory lock is invisible to anyone else.
* It does not make database and venue atomic. In dry-run the venue writes
  through the same session, so a rollback undoes everything; with a real venue
  the network call sits outside the transaction and a crash between "venue
  confirmed" and "commit" leaves the two out of step.
* The live path therefore needs a persistent guard plus reconciliation against
  the venue (NOTE/68). This module is the dry-run answer, not the live one.
"""

from __future__ import annotations

import asyncio

from backend.app.core.logging import get_logger

logger = get_logger("agent.perp_position_lock")


class PerpPositionLocks:
    """One :class:`asyncio.Lock` per ``position_id``, created on demand."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, position_id: str) -> asyncio.Lock:
        """Return the lock for this position, creating it if needed."""
        lock = self._locks.get(position_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[position_id] = lock
        return lock

    def is_held(self, position_id: str) -> bool:
        """True when someone currently owns this position's lock."""
        lock = self._locks.get(position_id)
        return bool(lock and lock.locked())

    def assert_held(self, position_id: str, *, caller: str) -> None:
        """Log loudly when an inner writer runs without the lock.

        Intentionally not an exception: a missing lock is a programming error we
        want to see immediately in the journal, but raising here would abort a
        close that is otherwise correct -- and refusing to close a position is
        worse than closing it unserialised. The test suite asserts on the
        contract; this catches a path added later that forgot it.
        """
        if not self.is_held(position_id):
            logger.error(
                "perp_position_lock_not_held",
                position_id=position_id,
                caller=caller,
                detail="perp position mutated outside the coordinator lock",
            )

    def discard(self, position_id: str) -> None:
        """Forget a closed position's lock.

        Called when a position reaches ``closed``: without this the registry
        would keep one entry per position ever opened for the lifetime of the
        process. Never called while the lock is held.
        """
        lock = self._locks.get(position_id)
        if lock is not None and not lock.locked():
            self._locks.pop(position_id, None)

    def tracked(self) -> int:
        """Number of positions with a lock in the registry (diagnostics)."""
        return len(self._locks)


_locks: PerpPositionLocks | None = None


def get_perp_position_locks() -> PerpPositionLocks:
    global _locks
    if _locks is None:
        _locks = PerpPositionLocks()
    return _locks
