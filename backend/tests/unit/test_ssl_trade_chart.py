"""Il dettaglio di un trade Smart SL deve portare il suo grafico.

Le vendite Smart SL erano l'unica famiglia di chiusure senza candele: la route
costruiva il grafico e il ramo `is_ssl` lo sostituiva con None prima di
rispondere. Qui si verifica che il grafico esca, che sia quello della vendita e
che le altre chiusure non cambino.

Eseguibile in locale: tocca solo la funzione di presentazione, non `agent.service`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from backend.app.api.routes.views import _perp_trade_detail
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.models.trades import PerpTrade

NOW = datetime(2026, 9, 3, 11, 33, tzinfo=UTC)


def _chart() -> dict:
    return {
        "entry_price": "100",
        "exit_price": "96",
        "opened_at": "2026-09-03T10:00:00+00:00",
        "closed_at": "2026-09-03T11:33:00+00:00",
        "candles": [
            {"timestamp": "2026-09-03T10:00:00+00:00", "open": 100, "high": 101, "low": 99, "close": 100},
            {"timestamp": "2026-09-03T11:30:00+00:00", "open": 99, "high": 99, "low": 96, "close": 96},
        ],
    }


def _position() -> PerpPosition:
    return PerpPosition(
        position_id="pos_x",
        user_id="u1",
        asset="INJ",
        side="long",
        size=Decimal("5"),
        entry_price=Decimal("100"),
        current_price=Decimal("96"),
        leverage=10,
        pnl_unrealized=Decimal("0"),
        status="open",
        opened_at=NOW,
        updated_at=NOW,
    )


def _trade(trade_id: str, notes: str) -> PerpTrade:
    return PerpTrade(
        trade_id=trade_id,
        position_id="pos_x",
        user_id="u1",
        asset="INJ",
        side="long",
        direction="close",
        size=Decimal("2.5"),
        price=Decimal("96"),
        leverage=10,
        status="confirmed",
        venue="dry_run",
        timestamp_utc=NOW,
        notes=notes,
        pnl_usd=Decimal("-10"),
    )


def test_smart_sl_trade_now_carries_its_chart() -> None:
    """Il difetto: qualunque cosa fosse stata calcolata, usciva None."""
    detail = _perp_trade_detail(
        _trade("ssl_pos_x_1c8299c2", "auto_close:smart_sl_sell_l1"),
        _position(),
        None,
        None,
        None,
        None,
        None,
        _chart(),
    )
    assert detail["is_smart_sl"] is True
    assert detail["chart"] is not None
    assert len(detail["chart"]["candles"]) == 2


def test_the_chart_is_the_one_of_that_sale() -> None:
    """Lo snapshot e' caricato per TRADE: il prezzo di uscita del grafico deve
    essere quello della vendita, non un valore della posizione."""
    detail = _perp_trade_detail(
        _trade("ssl_pos_x_1c8299c2", "auto_close:smart_sl_sell_l2"),
        _position(),
        None,
        None,
        None,
        None,
        None,
        _chart(),
    )
    assert str(detail["chart"]["exit_price"]) == "96"


def test_post_close_candles_reach_the_smart_sl_detail() -> None:
    """La route le calcola gia': prima venivano buttate con tutto il grafico."""
    post = [{"timestamp": "2026-09-03T11:35:00+00:00", "open": 96, "high": 97, "low": 96, "close": 97}]
    detail = _perp_trade_detail(
        _trade("ssl_pos_x_1c8299c2", "auto_close:smart_sl_sell_l1"),
        _position(),
        None,
        None,
        None,
        None,
        post,
        _chart(),
    )
    assert detail["chart"]["post_close_candles"] == post


def test_smart_sl_trade_without_snapshot_still_reports_no_chart() -> None:
    """I trade Smart SL anteriori al fix di NOTE/93 non hanno snapshot: il
    grafico resta assente e il client deve dirlo, non mostrare un riquadro
    vuoto. 32 trade su 96 in produzione sono in questo caso."""
    detail = _perp_trade_detail(
        _trade("ssl_pos_x_old00000", "auto_close:smart_sl_sell_l1"),
        _position(),
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert detail["is_smart_sl"] is True
    assert detail["chart"] is None


def test_smart_sl_specific_fields_are_untouched() -> None:
    """La correzione aggiunge il grafico: non deve togliere nulla di quanto il
    pannello Smart SL gia' mostrava."""
    detail = _perp_trade_detail(
        _trade("ssl_pos_x_1c8299c2", "auto_close:smart_sl_sell_l1"),
        _position(),
        None,
        None,
        None,
        None,
        None,
        _chart(),
    )
    assert detail["ssl_action"] == "sell"
    assert detail["ssl_level"] == "1"
    assert detail["pnl_usd"] is not None
    assert detail["size"] is not None


def test_ordinary_closes_are_unchanged() -> None:
    """Rete di regressione: il ramo non-SSL non e' stato toccato."""
    detail = _perp_trade_detail(
        _trade("cls_pos_x_11e615ce", "auto_close:take_profit_1_partial"),
        _position(),
        None,
        None,
        None,
        None,
        None,
        _chart(),
    )
    assert detail.get("is_smart_sl") is None
    assert detail["chart"] is not None
