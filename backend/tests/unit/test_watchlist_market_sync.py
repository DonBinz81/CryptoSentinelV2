"""Coerenza fra master watchlist e watchlist di mercato (spot/perp).

Regressione del bug "Errore salvataggio watchlist" del 16/08/2026: la lettura
ammetteva ogni simbolo `eligible`, la scrittura pretendeva che stesse nella
master. Bastava restringere la master perche' la lista di mercato persistita
contenesse simboli orfani: il client la rileggeva, la rispediva intera al primo
toggle e il backend rispondeva 400 su qualsiasi coin.
"""

from __future__ import annotations

import json

import pytest

from backend.app.agent.watchlist import (
    WATCHLIST_PERP_KEY,
    selected_perp_watchlist,
    selected_spot_watchlist,
    set_market_watchlist,
    set_selected_watchlist,
)
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

from backend.tests.unit.test_agent_step6 import USER_ID, db, settings  # noqa: F401


def _cfg():
    return settings(eligible_tokens=["BTC", "ETH", "SOL", "TRX", "ZEC"])


@pytest.mark.anyio
async def test_restringere_la_master_pota_le_watchlist_di_mercato(db) -> None:
    cfg = _cfg()
    set_selected_watchlist(cfg, ["BTC", "ETH", "TRX"])
    set_market_watchlist(cfg, "perp", ["BTC", "ETH", "TRX"])

    # La master perde TRX: la perp non deve conservarlo.
    set_selected_watchlist(cfg, ["BTC", "ETH"])

    assert json.loads(get_runtime_value(str(USER_ID), WATCHLIST_PERP_KEY)) == ["BTC", "ETH"]
    assert selected_perp_watchlist(cfg) == ["BTC", "ETH"]


@pytest.mark.anyio
async def test_la_lettura_di_mercato_ignora_i_simboli_fuori_master(db) -> None:
    """Difesa per lo stato gia' sporco nel DB (scritture manuali, versioni vecchie)."""
    cfg = _cfg()
    set_selected_watchlist(cfg, ["BTC", "ETH"])
    set_runtime_value(str(USER_ID), WATCHLIST_PERP_KEY, json.dumps(["BTC", "ETH", "ZEC"]))

    perp = selected_perp_watchlist(cfg)
    assert perp == ["BTC", "ETH"]

    # Cio' che il client rilegge deve essere ri-salvabile senza errori: e' questo
    # il ciclo che si rompeva (read -> toggle -> write dell'intera lista).
    assert set_market_watchlist(cfg, "perp", perp) == ["BTC", "ETH"]


@pytest.mark.anyio
async def test_errore_di_scrittura_elenca_tutti_i_simboli_fuori_master(db) -> None:
    cfg = _cfg()
    set_selected_watchlist(cfg, ["BTC", "ETH"])

    with pytest.raises(ValueError) as exc:
        set_market_watchlist(cfg, "spot", ["BTC", "TRX", "ZEC"])

    message = str(exc.value)
    assert "TRX" in message and "ZEC" in message


@pytest.mark.anyio
async def test_spot_e_perp_restano_indipendenti_dopo_la_potatura(db) -> None:
    cfg = _cfg()
    set_selected_watchlist(cfg, ["BTC", "ETH", "SOL", "TRX"])
    set_market_watchlist(cfg, "spot", ["BTC", "TRX"])
    set_market_watchlist(cfg, "perp", ["ETH", "SOL"])

    set_selected_watchlist(cfg, ["BTC", "ETH", "SOL"])

    assert selected_spot_watchlist(cfg) == ["BTC"]
    assert selected_perp_watchlist(cfg) == ["ETH", "SOL"]
