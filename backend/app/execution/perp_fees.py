"""PancakeSwap Perpetuals v2 — fee, funding e slippage fetcher.

Fee schedule PancakeSwap Perps v2 (BSC):
    Taker (market order):  apertura 0.06% + chiusura 0.06% = 0.12% round-trip
    Maker (limit order):   apertura 0.02% + chiusura 0.02% = 0.04% round-trip
Funding rate: ciclo 8h, caricato live per asset dall'API pubblica.
Slippage:     stimato da size vs open interest; si applica SOLO al taker
              (il maker non ha price impact perché non esegue a mercato).

I valori di fallback sono usati quando l'API è irraggiungibile.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx

from backend.app.core.logging import get_logger

logger = get_logger("execution.perp_fees")

# ── Costanti fee (fallback e confronto) ──────────────────────────────────────
TAKER_OPEN_RATE  = Decimal("0.0006")   # 0.06% — market order apertura
TAKER_CLOSE_RATE = Decimal("0.0006")   # 0.06% — market order chiusura
MAKER_OPEN_RATE  = Decimal("0.0002")   # 0.02% — limit order apertura
MAKER_CLOSE_RATE = Decimal("0.0002")   # 0.02% — limit order chiusura

# PancakeSwap Perps v2 REST API (pubblico, no auth)
_PCAKE_PERP_BASE  = "https://perp.pancakeswap.finance"
_TICKERS_PATH     = "/api/v2/tickers"
_TIMEOUT          = 5.0


@dataclass
class PerpFeeSnapshot:
    """Fotografia di tutti i costi per una posizione in un dato momento."""
    asset: str
    fee_mode: str                   # "taker" | "maker" | "none"
    taker_open_rate: Decimal        # frazione (es. 0.0006 = 0.06%)
    taker_close_rate: Decimal
    maker_open_rate: Decimal
    maker_close_rate: Decimal
    funding_rate_8h: Decimal        # frazione per ciclo 8h; positivo = long paga short
    price_impact_pct: Decimal       # slippage stimato %; rilevante solo per taker
    source: str                     # "live" | "fallback"


async def fetch_perp_fees(
    asset: str,
    size_usd: Decimal,
    fee_mode: str,
    base_url: str = _PCAKE_PERP_BASE,
) -> PerpFeeSnapshot:
    """Fetcha fee e funding live da PancakeSwap Perps v2.

    In caso di errore di rete usa i valori hardcoded e logga un warning.
    Le fee taker/maker sono sempre calcolate ENTRAMBE — anche in modalità
    "maker" il costo taker viene salvato per confronto.
    """
    funding_rate_8h = Decimal("0")
    price_impact_pct = Decimal("0")
    source = "fallback"

    if fee_mode != "none":
        try:
            symbol_dash  = f"{asset.upper()}-USDT"
            symbol_plain = f"{asset.upper()}USDT"
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(f"{base_url}{_TICKERS_PATH}")
                resp.raise_for_status()
                payload = resp.json()

            # L'API può restituire dict o list a seconda della versione
            if isinstance(payload, dict):
                data = (
                    payload.get(symbol_dash)
                    or payload.get(symbol_plain)
                    or payload.get(asset.upper())
                )
            elif isinstance(payload, list):
                data = next(
                    (t for t in payload if t.get("symbol") in (symbol_dash, symbol_plain)),
                    None,
                )
            else:
                data = None

            if data:
                raw_fr = (
                    data.get("fundingRate")
                    or data.get("funding_rate")
                    or data.get("lastFundingRate")
                    or 0
                )
                funding_rate_8h = Decimal(str(raw_fr))

                if fee_mode == "taker":
                    oi = float(
                        data.get("openInterest")
                        or data.get("open_interest")
                        or 0
                    )
                    if oi > 0:
                        impact = float(size_usd) / oi * 100
                        price_impact_pct = Decimal(str(round(min(impact, 5.0), 4)))

                source = "live"
            else:
                logger.warning("perp_fees_symbol_not_found", asset=asset)

        except Exception as exc:
            logger.warning("perp_fees_fetch_failed", asset=asset, error=str(exc))

    return PerpFeeSnapshot(
        asset=asset,
        fee_mode=fee_mode,
        taker_open_rate=TAKER_OPEN_RATE,
        taker_close_rate=TAKER_CLOSE_RATE,
        maker_open_rate=MAKER_OPEN_RATE,
        maker_close_rate=MAKER_CLOSE_RATE,
        funding_rate_8h=funding_rate_8h,
        price_impact_pct=price_impact_pct,
        source=source,
    )


def compute_opening_costs(
    snapshot: PerpFeeSnapshot,
    notional_usd: Decimal,
) -> dict:
    """Calcola tutti i costi di apertura dal fee snapshot.

    Restituisce sempre ENTRAMBI i valori (taker e maker) per confronto,
    più il costo effettivamente applicato in base a fee_mode.

    La voce 'applied_fee_usd' è quella che va in detrazione al P&L.
    """
    taker_fee_usd  = notional_usd * snapshot.taker_open_rate
    maker_fee_usd  = notional_usd * snapshot.maker_open_rate
    slippage_usd   = (
        notional_usd * snapshot.price_impact_pct / Decimal("100")
        if snapshot.fee_mode == "taker"
        else Decimal("0")
    )

    if snapshot.fee_mode == "taker":
        applied_fee_usd = taker_fee_usd + slippage_usd
    elif snapshot.fee_mode == "maker":
        applied_fee_usd = maker_fee_usd
    else:  # "none"
        applied_fee_usd = Decimal("0")

    return {
        "taker_fee_usd": taker_fee_usd,
        "maker_fee_usd": maker_fee_usd,
        "slippage_usd":  slippage_usd,
        "applied_fee_usd": applied_fee_usd,
        "price_impact_pct": snapshot.price_impact_pct,
        "funding_rate_8h": snapshot.funding_rate_8h,
    }


def accrue_funding(
    funding_rate_8h: Decimal,
    notional_usd: Decimal,
    hours_elapsed: float,
    side: str,
) -> Decimal:
    """Calcola il funding maturato per una posizione aperta.

    Convezione PancakeSwap Perps v2:
      funding_rate_8h > 0 → i long pagano gli short → costo per long, guadagno per short
      funding_rate_8h < 0 → gli short pagano i long → costo per short, guadagno per long
    """
    cycles = Decimal(str(hours_elapsed)) / Decimal("8")
    raw = notional_usd * funding_rate_8h * cycles
    # Il segno finale: long paga (negativo per il trader) se funding > 0
    return -raw if side == "long" else raw
