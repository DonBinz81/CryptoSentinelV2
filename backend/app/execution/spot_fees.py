"""PancakeSwap V3 spot AMM — fee e slippage stimati per dry-run.

Fee structure PancakeSwap V3 (BSC):
    Swap fee pool 0.05%: tier più comune per token/USDT liquidi.
    (Altri tier: 0.01% stablecoin, 0.25% long-tail)

Slippage: stimato al 0.10% default in dry-run (price impact tipico su pool
          con liquidità moderata).  In live è il DEX a calcolare lo slippage
          reale al momento dell'esecuzione — qui lo simuliamo.

Nota: sullo spot non esiste distinzione taker/maker come sul perp — le swap
AMM sono sempre eseguite a mercato.  La modalità 'all' applica entrambi i
costi; 'none' li esclude per studiare la strategia al lordo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.app.core.logging import get_logger

logger = get_logger("execution.spot_fees")

# ── Costanti fee ──────────────────────────────────────────────────────────────
SWAP_FEE_RATE         = Decimal("0.0005")   # 0.05% — pool tier standard PCS V3
DEFAULT_SLIPPAGE_RATE = Decimal("0.001")    # 0.10% — stima conservativa dry-run


@dataclass
class SpotFeeSnapshot:
    """Fotografia dei costi di apertura di una posizione spot."""
    fee_mode: str            # "all" | "none"
    swap_fee_rate: Decimal   # frazione (es. 0.0005 = 0.05%)
    slippage_rate: Decimal   # stima price impact


def compute_spot_costs(
    notional_usd: Decimal,
    fee_mode: str,
    slippage_rate: Decimal = DEFAULT_SLIPPAGE_RATE,
) -> dict:
    """Calcola swap fee + slippage per una posizione spot dry-run.

    Restituisce sempre entrambi i valori per visibilità, più applied_fee_usd
    che è l'importo effettivamente detratto dal P&L.
    """
    swap_fee_usd = notional_usd * SWAP_FEE_RATE
    slippage_usd = notional_usd * slippage_rate

    applied_fee_usd = (swap_fee_usd + slippage_usd) if fee_mode == "all" else Decimal("0")

    return {
        "swap_fee_usd":    swap_fee_usd,
        "slippage_usd":    slippage_usd,
        "applied_fee_usd": applied_fee_usd,
        "slippage_rate":   slippage_rate,
    }
