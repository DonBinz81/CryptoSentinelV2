"""Aster perp venue: read-only client and connection diagnostics.

This package contains no trading logic. Order placement, cancellation and
position changes are NOT implemented here on purpose: this phase only proves
that CryptoSentinelV2 can talk to its own Aster sub-account.
"""

from backend.app.execution.venues.aster.client import AsterClient, AsterError

__all__ = ["AsterClient", "AsterError"]
