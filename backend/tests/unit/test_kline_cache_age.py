"""Freschezza della cache delle candele: legata alla risoluzione, non fissa.

Eseguibile in locale come `test_interval_selector`: il modulo si carica per
percorso, evitando `routes/__init__` che tira dentro la catena web3/eth_account
senza wheel ARM64. Nessun database, nessuna rete.

Il problema che risolve, segnalato da David il 07/09: guardando una posizione
aperta il grafico non si aggiorna. Una delle cause e' qui — le candele venivano
servite dalla cache del motore di segnali con una validita' FISSA di 180
secondi, uguale per ogni risoluzione. Su 1m sono tre candele intere: chi guarda
vede una fotografia vecchia senza che nulla lo segnali.

La proprieta' che conta non e' la formula ma il COMPORTAMENTO: la stessa voce di
cache, con la stessa eta', dev'essere scartata su 1m e accettata su 15m. Un test
sulla sola formula passerebbe anche se nessuno la usasse.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]


def _views():
    """Carica views.py per percorso, senza passare dal pacchetto."""
    sys.path.insert(0, str(RADICE))
    spec = importlib.util.spec_from_file_location(
        "views_isolato_cache", RADICE / "backend" / "app" / "api" / "routes" / "views.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)  # type: ignore[union-attr]
    return modulo


V = _views()


# ── la validita' segue la dimensione della candela ─────────────────────────


def test_un_minuto_dura_mezza_candela() -> None:
    assert V._kline_cache_max_age("1m") == 30.0


def test_tre_minuti_dura_mezza_candela() -> None:
    assert V._kline_cache_max_age("3m") == 90.0


def test_cinque_minuti_dura_mezza_candela() -> None:
    assert V._kline_cache_max_age("5m") == 150.0


def test_oltre_i_sei_minuti_vale_il_tetto() -> None:
    """Sopra il tetto non si sale: 180s erano il valore storico ed e' il massimo."""
    for interval in ("15m", "30m", "1h", "4h", "1d"):
        assert V._kline_cache_max_age(interval) == 180.0, interval


def test_intervallo_sconosciuto_si_comporta_come_5m() -> None:
    """Un valore non in mappa non deve allungare la validita' per sbaglio."""
    assert V._kline_cache_max_age("qualcosa") == V._kline_cache_max_age("5m")


def test_mai_sotto_i_venti_secondi() -> None:
    """Il minimo protegge dal caso in cui qualcuno aggiunga una candela cortissima."""
    originale = dict(V._INTERVAL_MINUTES)
    try:
        V._INTERVAL_MINUTES["1s"] = 0
        assert V._kline_cache_max_age("1s") == 20.0
    finally:
        V._INTERVAL_MINUTES.clear()
        V._INTERVAL_MINUTES.update(originale)


# ── il comportamento, che e' il punto ──────────────────────────────────────


def _con_cache_di_eta(secondi: float, quante: int = 300):
    """Sostituisce il modulo delle klines con una voce di cache vecchia di N secondi.

    `_cached_klines` importa `get_kline_cache_entry` DENTRO la funzione, quindi
    va sostituito il modulo in `sys.modules` e non un attributo di `views`.
    """
    voce = types.SimpleNamespace(
        updated_at=datetime.now(UTC) - timedelta(seconds=secondi),
        candles=[{"t": i} for i in range(quante)],
    )
    finto = types.ModuleType("backend.app.agent.signals.perp.binance_klines")
    finto.get_kline_cache_entry = lambda **_: voce  # type: ignore[attr-defined]
    return finto


def _chiama(interval: str, eta_secondi: float):
    modulo = "backend.app.agent.signals.perp.binance_klines"
    precedente = sys.modules.get(modulo)
    sys.modules[modulo] = _con_cache_di_eta(eta_secondi)
    try:
        return V._cached_klines("futures", "BTCUSDT", interval, min_limit=100)
    finally:
        if precedente is not None:
            sys.modules[modulo] = precedente
        else:
            sys.modules.pop(modulo, None)


def test_stessa_cache_scartata_su_1m_e_accettata_su_15m() -> None:
    """Il cuore della modifica, in una riga sola.

    Sessanta secondi: su 1m e' una candela intera persa, su 15m e' la stessa
    identica immagine. Prima della modifica entrambe passavano, perche' il
    limite era 180s per tutti.
    """
    assert _chiama("1m", 60) is None, "su 1m una cache di 60s e' vecchia"
    assert _chiama("15m", 60) is not None, "su 15m la stessa cache va bene"


def test_su_1m_venti_secondi_bastano_ancora() -> None:
    assert _chiama("1m", 20) is not None


def test_su_3m_due_minuti_sono_troppi() -> None:
    """120s su 3m: passavano prima, ora no."""
    assert _chiama("3m", 120) is None


def test_su_3m_un_minuto_va_bene() -> None:
    assert _chiama("3m", 60) is not None


def test_il_tetto_storico_vale_ancora_sugli_intervalli_lunghi() -> None:
    """Su 1h nulla e' cambiato: sotto 180s si usa, sopra no."""
    assert _chiama("1h", 170) is not None
    assert _chiama("1h", 190) is None


def test_cache_troppo_corta_resta_scartata() -> None:
    """La modifica non deve aver toccato il controllo sul numero di candele."""
    modulo = "backend.app.agent.signals.perp.binance_klines"
    precedente = sys.modules.get(modulo)
    sys.modules[modulo] = _con_cache_di_eta(1, quante=10)
    try:
        assert V._cached_klines("futures", "BTCUSDT", "1m", min_limit=100) is None
    finally:
        if precedente is not None:
            sys.modules[modulo] = precedente
        else:
            sys.modules.pop(modulo, None)
