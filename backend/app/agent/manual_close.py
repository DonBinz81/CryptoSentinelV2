"""Pure decision logic for manual (human-initiated) perp position closes.

This module is deliberately free of web3, database and framework imports: it
is the layer where an arithmetic mistake would silently cost money, so it must
stay runnable on the developer machine. The project's Windows ARM64 workstation
cannot install the ``web3`` -> ``eth-account`` -> ``ckzg`` chain (no ARM64
wheels), which makes every module importing ``agent.service`` VPS-only. Keeping
this logic pure is what allows it to be unit-tested locally before deployment.

What lives here:

* the fixed preset percentages and the quantity quantum;
* how a percentage becomes a quantity on the CURRENT residual size;
* the "residual too small to trade" rule, which promotes a partial close to a
  full one instead of silently rounding;
* renormalisation of the ratchet and Smart SL states, so every automation keeps
  working on the reduced size after a manual partial close.

What does NOT live here: locking, persistence, venue calls, HTTP. Those belong
to the caller.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

#: The only percentages the first version accepts. No free percentage, no
#: slider: a wrong tap must not be able to produce an arbitrary size.
ALLOWED_PERCENTAGES: Final[tuple[int, ...]] = (25, 50, 75, 100)

#: Quantity granularity used across the perp engine (``_close_perp_position``
#: and the Smart SL already quantise to this). A real venue will additionally
#: impose stepSize/minQty/minNotional per symbol; that belongs to the live
#: execution layer, not here (NOTE/68).
QTY_QUANTUM: Final[Decimal] = Decimal("0.000001")

#: Canonical close reasons. They must stay distinct from ``manual_risk``, which
#: belongs to the different "close everything and pause" command, and from the
#: strategy reasons the regime guardian reacts to.
MANUAL_PARTIAL_CLOSE: Final[str] = "manual_partial_close"
MANUAL_FULL_CLOSE: Final[str] = "manual_full_close"

#: Order purpose persisted on ``perp_orders`` for manual closes, so a human
#: intervention is never confused with a time stop or a strategy exit.
MANUAL_CLOSE_PURPOSE: Final[str] = "manual"


class ManualCloseError(ValueError):
    """The request cannot be turned into a close plan."""


@dataclass(frozen=True)
class ClosePlan:
    """What a manual close request resolves to, before anything is executed."""

    requested_percentage: int
    fraction: Decimal
    close_qty: Decimal
    remaining_qty: Decimal
    is_full: bool
    close_reason: str
    #: True when a partial request had to become a full close because the
    #: residual would have been untradeable. Surfaced in the API response: the
    #: user asked for 75% and got 100%, and must be told.
    forced_full: bool

    @property
    def remaining_factor(self) -> Decimal:
        """Share of the position that survives this close, in [0, 1].

        This is the factor every size-derived state must be scaled by, and it
        is computed from the ACTUAL quantities rather than from the requested
        percentage: quantisation makes the two differ slightly, and the states
        must follow the quantity that was really closed.
        """
        total = self.close_qty + self.remaining_qty
        if total <= 0:
            return Decimal("0")
        return self.remaining_qty / total


def validate_percentage(percentage: Any) -> int:
    """Return the percentage as int, or raise if it is not an allowed preset."""
    try:
        value = int(percentage)
    except (TypeError, ValueError) as exc:
        raise ManualCloseError(f"percentage must be an integer, got {percentage!r}") from exc
    if value not in ALLOWED_PERCENTAGES:
        raise ManualCloseError(
            f"percentage must be one of {list(ALLOWED_PERCENTAGES)}, got {value}"
        )
    return value


def sizes_match(expected: Decimal | str | None, actual: Decimal) -> bool:
    """True when the size the client saw still matches the stored one.

    Compared at :data:`QTY_QUANTUM` granularity: below that the engine cannot
    trade the difference anyway, and an exact Decimal comparison would reject
    valid requests over digits nobody can act on. A ``None`` expectation means
    the client did not send one, which callers must treat as a rejection rather
    than as a match -- the check exists precisely to catch a position that moved
    under the user's feet.
    """
    if expected is None:
        return False
    expected_dec = expected if isinstance(expected, Decimal) else Decimal(str(expected))
    return expected_dec.quantize(QTY_QUANTUM) == actual.quantize(QTY_QUANTUM)


def build_close_plan(current_size: Decimal, percentage: Any) -> ClosePlan:
    """Turn a preset percentage into quantities on the CURRENT residual size.

    The percentage always applies to what is left now, never to the original
    size: a 50% after another 50% closes half of the half.

    Quantisation follows what the engine already does (``quantize`` with the
    default rounding), so introducing this path cannot move the numbers the
    golden test froze. The residual is then derived by subtraction, never
    quantised again, which keeps ``close_qty + remaining_qty == current_size``
    exactly.
    """
    pct = validate_percentage(percentage)
    if current_size <= 0:
        raise ManualCloseError("position size must be positive")

    fraction = Decimal(pct) / Decimal("100")
    if pct == 100:
        return ClosePlan(
            requested_percentage=pct,
            fraction=Decimal("1"),
            close_qty=current_size,
            remaining_qty=Decimal("0"),
            is_full=True,
            close_reason=MANUAL_FULL_CLOSE,
            forced_full=False,
        )

    close_qty = (current_size * fraction).quantize(QTY_QUANTUM)
    remaining_qty = current_size - close_qty

    # A residual below the quantum is not a position: it could never be closed
    # or protected afterwards, and leaving it open with size ~0 is exactly the
    # "open position with nothing in it" the engine already guards against.
    # Promote to a full close and say so, instead of rounding in silence.
    if remaining_qty < QTY_QUANTUM or close_qty <= 0:
        return ClosePlan(
            requested_percentage=pct,
            fraction=Decimal("1"),
            close_qty=current_size,
            remaining_qty=Decimal("0"),
            is_full=True,
            close_reason=MANUAL_FULL_CLOSE,
            forced_full=True,
        )

    return ClosePlan(
        requested_percentage=pct,
        fraction=fraction,
        close_qty=close_qty,
        remaining_qty=remaining_qty,
        is_full=False,
        close_reason=MANUAL_PARTIAL_CLOSE,
        forced_full=False,
    )


def _scaled_decimal_string(raw: Any, factor: Decimal) -> str | None:
    """Scale a Decimal-as-string state value, keeping it a string.

    Returns None when the value is absent or unparsable, so the caller can
    leave the original key untouched rather than corrupting it.
    """
    if raw is None:
        return None
    try:
        return str(Decimal(str(raw)) * factor)
    except Exception:
        return None


def renormalize_ratchet_state(state: dict | None, remaining_factor: Decimal) -> dict | None:
    """Rescale the ratchet base size after a manual partial close.

    The ratchet freezes ``base_size`` when it arms and closes cumulative
    fractions of it. After a manual reduction the base must shrink by the same
    factor, otherwise the next step would ask for a quantity computed on a size
    that no longer exists -- clamped by the engine to the whole residual, which
    would empty the position one step early.

    Deliberately preserved: ``closed_frac`` and ``last_step``. The ratchet keeps
    the stage it had reached; it is not re-armed, not advanced, not reset.
    """
    if not state:
        return state
    base = state.get("base_size")
    if base is None:
        # Not armed yet: nothing to rescale. When it arms later it will freeze
        # the already-reduced residual, which is the correct base.
        return state
    scaled = _scaled_decimal_string(base, remaining_factor)
    if scaled is None:
        return state
    new_state = dict(state)
    new_state["base_size"] = scaled
    return new_state


def renormalize_smart_sl_state(state: dict | None, remaining_factor: Decimal) -> dict | None:
    """Rescale every size-derived Smart SL value after a manual partial close.

    Two families of values are scaled:

    * ``original_size`` -- the base of both ``split_size`` (L1/L2 sell) and
      ``total_rebuy_size`` (above-entry rebuy). Left untouched, the levels would
      keep selling quantities computed on the pre-reduction size.
    * ``pre_sell_opening_fee`` / ``pre_sell_slippage`` / ``pre_sell_funding`` --
      per-level snapshots that a rebuy restores as ABSOLUTE values onto the
      position. Left untouched, a future rebuy would reinstate costs that belong
      to a larger position. The rebuy path is disarmed today
      (``perp_smart_sl_max_reentries = 0``), but the state must not be left
      inconsistent for the day it is switched back on.

    Deliberately preserved: level ``status`` (idle/sold/rebought), ``sell_price``
    and ``rebuy_fill_price`` (prices, not quantities), ``reentries`` and
    ``global_reentries`` (counters), ``realized_loss`` (already banked),
    ``original_entry`` / ``original_tp1`` / ``original_tp2`` (price levels) and
    ``protection_suspended``. No level is activated or deactivated here.
    """
    if not state:
        return state
    new_state = dict(state)

    scaled_size = _scaled_decimal_string(new_state.get("original_size"), remaining_factor)
    if scaled_size is not None:
        new_state["original_size"] = scaled_size

    levels = new_state.get("levels")
    if isinstance(levels, list):
        new_levels = []
        for level in levels:
            if not isinstance(level, dict):
                new_levels.append(level)
                continue
            new_level = dict(level)
            for key in ("pre_sell_opening_fee", "pre_sell_slippage", "pre_sell_funding"):
                scaled = _scaled_decimal_string(new_level.get(key), remaining_factor)
                if scaled is not None:
                    new_level[key] = scaled
            new_levels.append(new_level)
        new_state["levels"] = new_levels

    return new_state


def renormalize_states_json(
    ratchet_json: str | None,
    smart_sl_json: str | None,
    remaining_factor: Decimal,
) -> tuple[str | None, str | None]:
    """JSON-in / JSON-out wrapper over both renormalisations.

    Malformed JSON is left exactly as it was: a manual close must never be the
    operation that destroys a state blob it could not read.
    """
    def _load(raw: str | None) -> dict | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    ratchet_state = _load(ratchet_json)
    smart_sl_state = _load(smart_sl_json)

    new_ratchet = renormalize_ratchet_state(ratchet_state, remaining_factor)
    new_smart_sl = renormalize_smart_sl_state(smart_sl_state, remaining_factor)

    return (
        json.dumps(new_ratchet) if new_ratchet is not None else ratchet_json,
        json.dumps(new_smart_sl) if new_smart_sl is not None else smart_sl_json,
    )
