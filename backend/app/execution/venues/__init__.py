"""Perp execution venues behind one common contract.

Dry-run and live are not two different code paths any more: they are two
implementations of the same contract. The strategy asks for an action and reads
an ExecutionResult, without knowing whether it was simulated or sent to a DEX.
"""

from backend.app.execution.venues.base import ExecutionResult, PerpVenue
from backend.app.execution.venues.dry_run import DRY_RUN_VENUE, DryRunPerpVenue

__all__ = ["ExecutionResult", "PerpVenue", "DryRunPerpVenue", "DRY_RUN_VENUE"]
