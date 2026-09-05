"""Selettore della risoluzione del grafico: 1m/3m/5m scelti dall'utente.

Eseguibile in locale: il modulo viene caricato per percorso, evitando
``routes/__init__`` che tira dentro la catena web3/eth_account senza wheel
ARM64. Nessun database, nessuna rete.

Le due proprieta' che contano:

1. `intervals_available` dice il vero su cosa REGGE per un dato trade, usando
   la stessa formula del limite che sta in `_build_live_chart` — se la si
   duplicasse nel client, il giorno che cambia il selettore mentirebbe;

2. 🔴 la risoluzione scelta NON deve spostare il riferimento dello stop. Sono
   due cose che sembrano una sola (NOTE/57): il riferimento si ricava dalle
   ultime `lookback` CANDELE prima dell'apertura, quindi a 5m guarda 100 minuti
   di storia e a 1m ne guarda 20. Un livello di stop che cambia a seconda di
   come guardi il grafico e' un livello sbagliato.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]


def _views():
    """Carica views.py per percorso, senza passare dal pacchetto."""
    sys.path.insert(0, str(RADICE))
    spec = importlib.util.spec_from_file_location(
        "views_isolato", RADICE / "backend" / "app" / "api" / "routes" / "views.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)  # type: ignore[union-attr]
    return modulo


V = _views()
APERTURA = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


# ── quali risoluzioni reggono ──────────────────────────────────────────────


def test_1m_regge_sui_trade_corti() -> None:
    """Fino a ~4 ore: e' la maggioranza dei trade perp."""
    assert "1m" in V._intervals_available(60)
    assert "1m" in V._intervals_available(2 * 60)
    assert "1m" in V._intervals_available(4 * 60)


def test_1m_non_e_offerto_quando_non_entrerebbe() -> None:
    """Oltre le ~4 ore la finestra a 1m non entra nel tetto per richiesta.

    Il selettore deve DISABILITARLA, non mostrarla e poi disegnare una parte
    della storia come se fosse tutta.
    """
    assert "1m" not in V._intervals_available(8 * 60)
    assert "1m" not in V._intervals_available(24 * 60)


def test_3m_arriva_a_dodici_ore() -> None:
    assert "3m" in V._intervals_available(12 * 60)
    assert "3m" not in V._intervals_available(24 * 60)


def test_un_trade_lungo_lascia_sempre_qualcosa_di_scegliibile() -> None:
    """Anche su un trade di giorni resta almeno una risoluzione utilizzabile."""
    for ore in (24, 48, 24 * 30):
        assert V._intervals_available(ore * 60), f"nessun intervallo per {ore}h"


def test_solo_intervalli_che_binance_conosce() -> None:
    assert set(V.SELECTABLE_INTERVALS) <= set(V._INTERVAL_MINUTES)
    assert "2m" not in V.SELECTABLE_INTERVALS


# ── 🔴 il riferimento dello stop non dipende dalla risoluzione ─────────────


def _grafico(per_min: int, n: int = 60) -> dict:
    """Stessa storia di mercato: un tuffo a 60 minuti dall'apertura.

    A 5m le ultime 20 candele coprono 100 minuti e lo vedono; a 1m ne coprono
    20 e non lo vedono.
    """
    candele = []
    for i in range(n, 0, -1):
        t = APERTURA - timedelta(minutes=i * per_min)
        minuti_prima = (APERTURA - t).total_seconds() / 60
        basso = 50.0 if abs(minuti_prima - 60) < per_min / 2 + 0.01 else 98.0
        candele.append({"t": t.isoformat(), "o": 99, "h": 100.0, "l": basso, "c": 99})
    return {"opened_at": APERTURA.isoformat(), "candles": candele}


def test_il_rischio_e_reale_non_teorico() -> None:
    """Prima di proteggersi da un difetto, dimostrare che esiste.

    Se un giorno questo test cominciasse a passare "da solo" (riferimenti
    uguali), vorrebbe dire che l'inferenza e' cambiata — e la protezione qui
    sotto andrebbe rivalutata, non tolta.
    """
    a5 = V._infer_stop_reference_from_chart(_grafico(5), "perp", "long", 20)
    a1 = V._infer_stop_reference_from_chart(_grafico(1), "perp", "long", 20)
    assert a5 is not None and a1 is not None
    assert a5["price"] != a1["price"], (
        "la stessa storia deve dare riferimenti diversi a risoluzioni diverse: "
        "e' la ragione per cui l'inferenza va saltata con un intervallo imposto"
    )
    assert float(a5["price"]) == 50.0, "a 5m il tuffo e' dentro la finestra"
    assert float(a1["price"]) == 98.0, "a 1m il tuffo e' fuori dalla finestra"


def test_un_long_usa_il_minimo_non_il_massimo() -> None:
    """Verificato leggendo `_stop_reference_field`, non assunto.

    La prima stesura di questi test dava per scontato il massimo e misurava la
    cosa sbagliata: passava senza provare niente.
    """
    assert V._stop_reference_field("perp", "long") == "low"
    assert V._stop_reference_field("perp", "short") == "high"


# ── la protezione e' DAVVERO agganciata, non solo scritta ──────────────────
#
# I test sopra dimostrano che il rischio esiste. Questi dimostrano che il
# codice se ne difende: senza, passerebbero comunque — ed e' esattamente il
# caso di "test che non vede il difetto" raccolto in NOTE/113 §3-bis.
#
# Il fetch verso Binance fallisce (nessuna rete nei test) e la funzione ripiega
# sulle candele che ha: e' il ramo che ci serve, perche' li' si decide se
# inferire il riferimento o conservarlo.


def _grafico_senza_riferimento() -> dict:
    """Candele che PRODURREBBERO un riferimento, ma nessuno registrato."""
    g = _grafico(5)
    g["closed_at"] = (APERTURA + timedelta(hours=1)).isoformat()
    g["interval"] = "5m"
    return g


async def test_senza_intervallo_imposto_il_riferimento_viene_inferito() -> None:
    """Comportamento storico, che non deve cambiare."""
    risultato = await V._enrich_trade_chart_context(
        _grafico_senza_riferimento(), "LINK", "futures", "perp", "long", None, 20, None
    )
    assert risultato is not None
    assert risultato.get("stop_reference"), "senza scelta utente l'inferenza resta"


async def test_con_intervallo_imposto_il_riferimento_NON_viene_inferito() -> None:
    """🔴 Il punto di tutto: la risoluzione non deve creare un livello di stop.

    Se questo test fallisce, la riga SL mostrata cambia a seconda di come si
    guarda il grafico — un livello plausibile e falso.
    """
    risultato = await V._enrich_trade_chart_context(
        _grafico_senza_riferimento(), "LINK", "futures", "perp", "long", None, 20, "1m"
    )
    assert risultato is not None
    assert not risultato.get("stop_reference"), (
        "con una risoluzione scelta dall'utente il riferimento non va inventato: "
        "meglio assente che dipendente dallo zoom"
    )


# ── 🔴 anche il percorso della posizione APERTA, che nella prima stesura ────
#     era rimasto scoperto (trovato da una revisione avversariale).
#
# La protezione esisteva solo per i trade chiusi. Su una posizione aperta
# `_build_live_chart` chiamava `_ensure_stop_reference` sulle candele appena
# scaricate alla risoluzione scelta dall'utente.
#
# Oggi il ramo e' inerte in produzione (tutte le posizioni aperte hanno
# `stop_reference_time`), ma "inerte oggi" e' quello che si era detto anche del
# percorso chiuso, dove poi sono emersi 7 snapshot senza riferimento.


class _PosizioneSenzaRiferimento:
    """Posizione aperta priva di stop_reference_time: il caso che scopre il ramo."""

    asset = "LINK"
    side = "long"
    entry_price = "100"
    current_price = "99"
    stop_loss = "95"
    initial_stop_loss = None
    take_profit_1 = None
    take_profit_2 = None
    liquidation_price = None
    stop_reference_time = None
    stop_reference_price = None
    stop_reference_field = None
    opened_at = APERTURA


def _stub_moduli(monkeypatch, per_min_atteso: dict):
    """Feed e _auto_chart_interval finti: senza, la funzione esce prima di
    arrivare al punto che vogliamo osservare — ed e' esattamente cosi' che la
    prima stesura di questo test passava anche col difetto presente."""
    import types

    # service.py non e' importabile in locale (web3 senza wheel ARM64): copia
    # identica della funzione, da service.py:166-174.
    serv = types.ModuleType("backend.app.agent.service")

    def _auto(duration_min):
        if duration_min <= 6 * 60:
            return "5m", 5
        if duration_min <= 2 * 24 * 60:
            return "1h", 60
        if duration_min <= 30 * 24 * 60:
            return "4h", 240
        return "1d", 1440

    serv._auto_chart_interval = _auto
    monkeypatch.setitem(sys.modules, "backend.app.agent.service", serv)

    class _Candela:
        def __init__(self, t, o, h, l, c):
            self.timestamp, self.open, self.high, self.low, self.close = t, o, h, l, c

    class _Feed:
        def __init__(self, *a, **k):
            pass

        async def fetch(self, *, symbol, interval, limit, market, start_time=None):
            per_min = V._INTERVAL_MINUTES[interval]
            per_min_atteso["visto"] = interval
            base = start_time or (APERTURA - timedelta(minutes=per_min * limit))
            fuori = []
            for i in range(limit):
                t = base + timedelta(minutes=i * per_min)
                minuti_prima = (APERTURA - t).total_seconds() / 60
                basso = 50.0 if 55 < minuti_prima <= 65 else 98.0
                fuori.append(_Candela(t, 99, 100.0, basso, 99))
            return fuori

    mod = types.ModuleType("backend.app.agent.signals.perp.binance_klines")
    mod.BinanceKlineFeed = _Feed
    monkeypatch.setitem(sys.modules, "backend.app.agent.signals.perp.binance_klines", mod)


async def test_posizione_aperta_SENZA_scelta_utente_inferisce(monkeypatch) -> None:
    """Comportamento storico: senza intervallo imposto il riferimento si deduce."""
    _stub_moduli(monkeypatch, {})
    monkeypatch.setattr(V, "_cached_klines", lambda *a, **k: None, raising=False)
    r = await V._build_live_chart(_PosizioneSenzaRiferimento(), "perp", settings=None)
    assert r is not None and r.get("stop_reference"), "senza scelta utente l inferenza resta"


async def test_posizione_aperta_con_intervallo_scelto_NON_inferisce(monkeypatch) -> None:
    """🔴 Il difetto trovato dalla revisione: qui la protezione mancava.

    Se fallisce, la candela indicata come origine dello stop — e in assenza di
    `initial_stop_loss` la riga SL stessa — cambiano a seconda della
    risoluzione con cui si guarda il grafico.
    """
    visto: dict = {}
    _stub_moduli(monkeypatch, visto)
    monkeypatch.setattr(V, "_cached_klines", lambda *a, **k: None, raising=False)
    r = await V._build_live_chart(
        _PosizioneSenzaRiferimento(), "perp", settings=None, interval_override="1m"
    )
    assert r is not None, "il feed finto deve produrre un grafico"
    assert visto.get("visto") == "1m", "la risoluzione scelta deve arrivare al feed"
    assert not r.get("stop_reference"), (
        "con una risoluzione scelta dall utente il riferimento non va dedotto: "
        "meglio assente che dipendente dallo zoom"
    )
