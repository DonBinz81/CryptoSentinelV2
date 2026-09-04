"""Marker delle chiusure manuali sul grafico e percentuale sulle righe di storico.

Due letture diverse della stessa cosa, con nomi diversi apposta:
`manual_reduced_pct` sulla posizione è cumulativo, `manual_close_pct` sulla riga
di storico è il singolo evento. Qui si verifica che restino distinti e che i
marker fuori dalla finestra del grafico non arrivino mai al client.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backend.app.api.routes.views import _manual_close_markers, _perp_trade_detail
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.views import _manual_close_pct

T0 = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)


def _chart(n: int = 5) -> dict:
    return {
        "entry_price": "100",
        "exit_price": "96",
        # _trade_timeline legge chart["opened_at"] direttamente: un grafico di
        # prova senza queste chiavi fa esplodere il dettaglio, non i marker.
        "opened_at": T0.isoformat(),
        "closed_at": (T0 + timedelta(minutes=20)).isoformat(),
        "candles": [
            {"t": (T0 + timedelta(minutes=5 * i)).isoformat(), "o": 100, "h": 101, "l": 99, "c": 100}
            for i in range(n)
        ],
    }


def _manual(at: datetime, size: str = "5", price: str = "98") -> PerpTrade:
    return PerpTrade(
        trade_id=f"cls_pos_x_{int(at.timestamp())}",
        position_id="pos_x",
        user_id="u1",
        asset="LINK",
        side="long",
        direction="close",
        size=Decimal(size),
        price=Decimal(price),
        leverage=10,
        status="confirmed",
        venue="dry_run",
        timestamp_utc=at,
        notes="manual_close:manual_partial_close",
        pnl_usd=Decimal("1"),
    )


def _position() -> PerpPosition:
    return PerpPosition(
        position_id="pos_x",
        user_id="u1",
        asset="LINK",
        side="long",
        size=Decimal("5"),
        entry_price=Decimal("100"),
        current_price=Decimal("96"),
        leverage=10,
        pnl_unrealized=Decimal("0"),
        status="open",
        opened_at=T0,
        updated_at=T0,
    )


# ── marker dentro e fuori la finestra ──────────────────────────────────────


def test_event_inside_the_window_becomes_a_marker() -> None:
    markers = _manual_close_markers(_chart(), [_manual(T0 + timedelta(minutes=10))], Decimal("10"))
    assert len(markers) == 1
    assert Decimal(markers[0]["price"]) == Decimal("98")
    assert Decimal(markers[0]["size"]) == Decimal("5")
    assert markers[0]["pct"] == "50.00"


def test_event_before_the_window_is_dropped() -> None:
    """Il client aggancia il timestamp alla candela piu' vicina e "piu' vicina"
    non fallisce mai: un evento fuori range verrebbe disegnato su una candela di
    bordo, in un punto dove quella chiusura non e' avvenuta."""
    markers = _manual_close_markers(_chart(), [_manual(T0 - timedelta(hours=3))], Decimal("10"))
    assert markers == []


def test_event_after_the_window_is_dropped() -> None:
    markers = _manual_close_markers(_chart(), [_manual(T0 + timedelta(hours=3))], Decimal("10"))
    assert markers == []


def test_only_the_events_inside_survive() -> None:
    dentro = _manual(T0 + timedelta(minutes=5))
    fuori = _manual(T0 + timedelta(days=1))
    markers = _manual_close_markers(_chart(), [dentro, fuori], Decimal("10"))
    assert len(markers) == 1


def test_boundary_events_are_kept() -> None:
    """Prima e ultima candela incluse: il confronto e' inclusivo."""
    prima, ultima = T0, T0 + timedelta(minutes=20)
    markers = _manual_close_markers(_chart(), [_manual(prima), _manual(ultima)], Decimal("10"))
    assert len(markers) == 2


def test_no_chart_means_no_markers() -> None:
    assert _manual_close_markers(None, [_manual(T0)], Decimal("10")) == []


def test_chart_without_candles_produces_no_markers() -> None:
    assert _manual_close_markers({"candles": []}, [_manual(T0)], Decimal("10")) == []


def test_unknown_opening_size_still_marks_the_event_without_percentage() -> None:
    markers = _manual_close_markers(_chart(), [_manual(T0 + timedelta(minutes=5))], None)
    assert len(markers) == 1
    assert markers[0]["pct"] is None


# ── la lista arriva sempre quando c'e' un grafico ──────────────────────────


def test_the_list_is_present_and_empty_when_there_are_no_manual_closes() -> None:
    """Vuota, non assente: il client non deve distinguere due casi."""
    detail = _perp_trade_detail(
        _manual(T0), _position(), None, None, None, None, None, _chart(), [], None
    )
    assert detail["chart"]["manual_closes"] == []


def test_the_markers_reach_the_detail_payload() -> None:
    detail = _perp_trade_detail(
        _manual(T0), _position(), None, None, None, None, None, _chart(),
        [_manual(T0 + timedelta(minutes=5))], Decimal("10"),
    )
    assert len(detail["chart"]["manual_closes"]) == 1


# ── percentuale per evento sulle righe di storico ──────────────────────────


def test_history_percentage_is_per_event_not_cumulative() -> None:
    """Due chiusure sulla stessa posizione: la seconda dice quanto ha tolto LEI.

    Con la cumulativa le due righe direbbero "50%" e "75%" e sembrerebbero due
    riduzioni di dimensione diversa, mentre la seconda ha tolto il 25%.
    """
    openings = {"pos_x": Decimal("10")}
    prima = _manual(T0, size="5")
    seconda = _manual(T0 + timedelta(hours=1), size="2.5")
    assert _manual_close_pct(prima, openings) == "50.00"
    assert _manual_close_pct(seconda, openings) == "25.00"


def test_non_manual_rows_have_no_percentage() -> None:
    automatico = _manual(T0)
    automatico.notes = "auto_close:take_profit_1_partial"
    assert _manual_close_pct(automatico, {"pos_x": Decimal("10")}) is None


def test_percentage_is_none_when_the_opening_size_is_unknown() -> None:
    assert _manual_close_pct(_manual(T0), {}) is None
    assert _manual_close_pct(_manual(T0), {"pos_x": Decimal("0")}) is None


# ── il difetto trovato sui dati di produzione (chat C, 4 settembre) ─────────


def test_close_inside_the_last_candle_is_kept() -> None:
    """Il marker che conta di piu' cadeva sempre fuori.

    Un timestamp di candela e' il suo istante di APERTURA. Usando l'apertura
    dell'ultima candela come limite superiore, ogni evento avvenuto DENTRO
    quella candela veniva scartato — e la chiusura di una posizione sta li' per
    costruzione, perche' il grafico di un trade chiuso viene tagliato proprio
    sulla candela della chiusura. Risultato in produzione: 4 trade su 4 senza il
    marker della chiusura, mentre le riduzioni precedenti passavano.

    Caso reale: BCH, ultima candela 22:35:00, chiusura 22:35:49.
    """
    ultima_apertura = T0 + timedelta(minutes=20)
    chiusura = ultima_apertura + timedelta(seconds=49)
    markers = _manual_close_markers(_chart(), [_manual(chiusura)], Decimal("10"))
    assert len(markers) == 1, "il marker della chiusura non deve sparire"


def test_events_at_any_second_inside_a_candle_are_kept() -> None:
    """I test precedenti usavano orari allineati alle candele e non potevano
    vedere il difetto: era la finzione del test a nasconderlo. Qui gli orari
    cadono a caso dentro l'intervallo, come nella realta'."""
    base = T0 + timedelta(minutes=20)
    for secondi in (1, 30, 59, 299):
        markers = _manual_close_markers(
            _chart(), [_manual(base + timedelta(seconds=secondi))], Decimal("10")
        )
        assert len(markers) == 1, f"scartato un evento a +{secondi}s dall'apertura"


def test_event_past_the_end_of_the_last_candle_is_still_dropped() -> None:
    """Il limite si estende di UN intervallo, non oltre: la zona post-chiusura
    resta esclusa."""
    oltre = T0 + timedelta(minutes=20) + timedelta(minutes=5, seconds=1)
    assert _manual_close_markers(_chart(), [_manual(oltre)], Decimal("10")) == []


def test_the_interval_declared_by_the_chart_is_honoured() -> None:
    """Su un grafico a 1h la finestra si estende di un'ora, non di cinque minuti."""
    chart = _chart()
    chart["interval"] = "1h"
    dentro = T0 + timedelta(minutes=20) + timedelta(minutes=45)
    assert len(_manual_close_markers(chart, [_manual(dentro)], Decimal("10"))) == 1
