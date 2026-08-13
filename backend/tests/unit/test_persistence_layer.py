"""Step 5 persistence layer tests: DB, repositories, migration, backup, views."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.persistence import database
from backend.app.persistence.backup import backup_db
from backend.app.persistence.database import check_db, close_db, get_session_factory, init_db
from backend.app.persistence.migration import migrate_json_to_db
from backend.app.persistence.archive import archive_dry_run_records, list_archived_runs, reset_all_data
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.decisions import AgentDecisionRepository
from backend.app.persistence.repositories.device_tokens import DeviceTokenRepository
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.positions import (
    PerpPositionRepository,
    SpotPositionRepository,
)
from backend.app.persistence.repositories.trades import PerpTradeRepository, SpotTradeRepository
from backend.app.persistence.repositories.x402_budget import X402BudgetRepository
from backend.app.persistence.views import ViewService

USER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
async def db(tmp_path: Path):
    # Reset module globals so each test gets a clean engine.
    database._engine = None
    database._session_factory = None
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    await init_db(url)
    yield url
    await close_db()


@pytest.mark.asyncio
async def test_check_db_reports_connected_with_latency(db) -> None:
    health = await check_db()
    assert health["connected"] is True
    assert "latency_ms" in health


@pytest.mark.asyncio
async def test_check_db_reports_disconnected_when_uninitialised() -> None:
    database._engine = None
    database._session_factory = None
    health = await check_db()
    assert health["connected"] is False


@pytest.mark.asyncio
async def test_json_migration_is_idempotent(db, tmp_path: Path) -> None:
    tokens_file = tmp_path / "fcm_tokens.json"
    tokens_file.write_text(
        json.dumps(
            {
                "tokens": [
                    {
                        "token_id": "abc123",
                        "token": "raw-token",
                        "user_id": USER,
                        "platform": "android",
                        "device_id": None,
                        "app_version": "1.0",
                        "locale": "it",
                        "created_at": "2026-06-15T10:00:00+00:00",
                        "updated_at": "2026-06-15T10:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    alerts_file = tmp_path / "alerts.json"
    alerts_file.write_text(
        json.dumps({"config": {"price_alerts": []}, "state": {"triggered_keys": ["x"]}}),
        encoding="utf-8",
    )

    factory = get_session_factory()
    async with factory() as session:
        await migrate_json_to_db(
            session, fcm_tokens_path=str(tokens_file), alerts_path=str(alerts_file)
        )
    # Second run must not duplicate.
    async with factory() as session:
        await migrate_json_to_db(
            session, fcm_tokens_path=str(tokens_file), alerts_path=str(alerts_file)
        )

    async with factory() as session:
        repo = DeviceTokenRepository(session)
        assert await repo.count() == 1
        assert await repo.tokens_for_user(USER) == ["raw-token"]


@pytest.mark.asyncio
async def test_x402_budget_persists_across_sessions(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = X402BudgetRepository(session)
        assert await repo.load_today(USER) == Decimal("0")
        await repo.save(USER, Decimal("0.20"))
    async with factory() as session:
        repo = X402BudgetRepository(session)
        assert await repo.load_today(USER) == Decimal("0.20")


@pytest.mark.asyncio
async def test_spot_trade_repo_save_and_list(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = SpotTradeRepository(session)
        await repo.save(
            SpotTrade(
                trade_id="t1",
                user_id=USER,
                asset="BNB",
                side="buy",
                amount=Decimal("1.5"),
                price=Decimal("600"),
                amount_quote=Decimal("900"),
                status="confirmed",
                timestamp_utc=datetime.now(UTC),
                block_timestamp_utc=datetime.now(UTC),
            )
        )
        trades = await repo.list_for_user(USER)
        assert len(trades) == 1
        assert trades[0].asset == "BNB"
        # UTC and on-chain timestamps are stored separately.
        assert trades[0].timestamp_utc is not None
        assert trades[0].block_timestamp_utc is not None


def test_spot_trade_detail_closed_uses_position_levels() -> None:
    from backend.app.api.routes.views import _spot_trade_detail

    now = datetime.now(UTC)
    pos = SpotPosition(
        position_id="pos1", user_id=USER, asset="BTC", size=Decimal("1"),
        entry_price=Decimal("100"), current_price=Decimal("105"),
        stop_loss=Decimal("95"), take_profit_1=Decimal("103"), take_profit_2=Decimal("106"),
        status="closed", opened_at=now, updated_at=now,
    )
    close_trade = SpotTrade(
        trade_id="cls_pos1_abc12345", user_id=USER, asset="BTC", side="sell",
        amount=Decimal("1"), price=Decimal("105"), amount_quote=Decimal("105"),
        status="confirmed", timestamp_utc=now, pnl_usd=Decimal("5"),
        notes="auto_close:take_profit_2",
    )
    detail = _spot_trade_detail(close_trade, pos, None, None)
    # Entry e uscita NON devono coincidere; livelli e timeline popolati.
    assert detail["entry_price"] == "100.00"
    assert detail["current_or_exit_price"] == "105.00"
    assert detail["stop_loss"] == "95.00"
    assert detail["take_profit_1"] == "103.00"
    assert detail["take_profit_2"] == "106.00"
    assert detail["closed_at"] is not None
    assert detail["pnl_usd"] == "+5.00"
    assert detail["size"] == "1.00"


@pytest.mark.asyncio
async def test_win_rate_uses_pnl_sign(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = SpotTradeRepository(session)
        now = datetime.now(UTC)
        # Apertura senza pnl (esclusa dal calcolo) + 2 chiusure: 1 vincente, 1 perdente.
        await repo.save(SpotTrade(
            trade_id="open", user_id=USER, asset="BNB", side="buy",
            amount=Decimal("1"), price=Decimal("100"), amount_quote=Decimal("100"),
            status="prepared", timestamp_utc=now,
        ))
        await repo.save(SpotTrade(
            trade_id="win", user_id=USER, asset="BNB", side="sell",
            amount=Decimal("1"), price=Decimal("110"), amount_quote=Decimal("110"),
            status="confirmed", timestamp_utc=now, notes="auto_close:trailing_stop",
            pnl_usd=Decimal("10"),
        ))
        await repo.save(SpotTrade(
            trade_id="loss", user_id=USER, asset="BNB", side="sell",
            amount=Decimal("1"), price=Decimal("95"), amount_quote=Decimal("95"),
            status="confirmed", timestamp_utc=now, notes="auto_close:stop_loss",
            pnl_usd=Decimal("-5"),
        ))
    async with factory() as session:
        win = await SpotTradeRepository(session).win_rate(USER)
        # 2 chiusure, 1 vincente (anche se chiusa per trailing_stop, conta perche' pnl>0).
        assert win["total"] == 2
        assert win["wins"] == 1
        assert win["win_rate_pct"] == 50.0


@pytest.mark.asyncio
async def test_perp_position_carries_leverage_and_liquidation(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = PerpPositionRepository(session)
        now = datetime.now(UTC)
        await repo.save(
            PerpPosition(
                position_id="p1",
                user_id=USER,
                asset="ETH",
                side="long",
                size=Decimal("2"),
                entry_price=Decimal("3000"),
                current_price=Decimal("3050"),
                leverage=3,
                liquidation_price=Decimal("2100"),
                funding_rate=Decimal("0.0001"),
                opened_at=now,
                updated_at=now,
            )
        )
        positions = await repo.open_for_user(USER)
        assert positions[0].leverage == 3
        assert positions[0].liquidation_price == Decimal("2100")


@pytest.mark.asyncio
async def test_portfolio_upsert_and_snapshot(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = PnlRepository(session)
        await repo.upsert_portfolio(
            USER,
            total_equity_usd=Decimal("1000"),
            initial_equity_usd=Decimal("1000"),
            peak_equity_usd=Decimal("1000"),
        )
        await repo.upsert_portfolio(
            USER,
            total_equity_usd=Decimal("1100"),
            drawdown_pct=Decimal("-2.0"),
        )
        portfolio = await repo.get_portfolio(USER)
        assert portfolio.total_equity_usd == Decimal("1100")
        assert portfolio.initial_equity_usd == Decimal("1000")

        await repo.save_snapshot(
            PnlSnapshot(
                user_id=USER,
                timestamp_utc=datetime.now(UTC),
                total_equity_usd=Decimal("1100"),
                drawdown_pct=Decimal("-2.0"),
            )
        )
        snaps = await repo.recent_for_user(USER)
        assert len(snaps) == 1


@pytest.mark.asyncio
async def test_decision_repo_records_reasoning(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = AgentDecisionRepository(session)
        await repo.save(
            AgentDecision(
                decision_id="d1",
                user_id=USER,
                timestamp_utc=datetime.now(UTC),
                asset="BNB",
                market="spot",
                action="enter",
                confidence=Decimal("0.82"),
                reasoning="VWAP reclaim with volume spike",
            )
        )
        decisions = await repo.recent_for_user(USER)
        assert decisions[0].action == "enter"
        assert "VWAP" in decisions[0].reasoning


@pytest.mark.asyncio
async def test_global_view_assembles_from_portfolio(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        pnl = PnlRepository(session)
        await pnl.upsert_portfolio(
            USER,
            total_equity_usd=Decimal("1100"),
            initial_equity_usd=Decimal("1000"),
            peak_equity_usd=Decimal("1150"),
            drawdown_pct=Decimal("-4.3"),
            max_drawdown_pct=Decimal("-6.0"),
            exposure_pct=Decimal("12.0"),
            agent_status="running",
            trades_today=2,
        )
        # global_view ricalcola total_equity = initial + realized + unrealized:
        # un trade realizzato da +100 porta l'equity a 1100.
        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id="gv1",
                user_id=USER,
                asset="BNB",
                side="sell",
                amount=Decimal("1"),
                price=Decimal("100"),
                amount_quote=Decimal("100"),
                status="confirmed",
                provider="agent",
                timestamp_utc=datetime.now(UTC),
                pnl_usd=Decimal("100"),
            )
        )
    async with factory() as session:
        view = await ViewService(session, drawdown_cap_pct=-15.0).global_view(USER)
        assert view.total_equity_usd == Decimal("1100")
        assert view.pnl_total_usd == Decimal("100")
        assert view.pnl_total_pct == 10.0
        assert view.drawdown_cap_pct == -15.0
        assert view.agent_status == "running"


@pytest.mark.asyncio
async def test_global_view_without_portfolio_uses_base_equity(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        view = await ViewService(
            session,
            drawdown_cap_pct=-15.0,
            daily_loss_limit_pct=-8.0,
            min_portfolio_value_usd=5.0,
            base_equity_usd=Decimal("200"),
        ).global_view(USER)

    assert view.total_equity_usd == Decimal("200")
    assert view.initial_equity_usd == Decimal("200")
    assert view.drawdown_pct == Decimal("0")
    assert view.max_drawdown_pct == Decimal("0")
    assert view.risk_guardrail is None


@pytest.mark.asyncio
async def test_global_view_perp_exposure_is_margin_not_notional(db) -> None:
    """L'esposizione perp deve essere il MARGINE (nozionale/leva), non il nozionale,
    così riflette il capitale realmente consumato dall'equity."""
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("1000"), initial_equity_usd=Decimal("1000"),
            peak_equity_usd=Decimal("1000"),
        )
        # entry 100 * size 10 = 1000 nozionale; leva 10 -> margine 100.
        await PerpPositionRepository(session).save(
            PerpPosition(
                position_id="pp-exp", user_id=USER, asset="ETH", side="long",
                size=Decimal("10"), entry_price=Decimal("100"), current_price=Decimal("100"),
                leverage=10, opened_at=now, updated_at=now,
            )
        )
        await session.commit()
    async with factory() as session:
        view = await ViewService(session, drawdown_cap_pct=-15.0).global_view(USER)
        assert view.perp_exposure_usd == Decimal("100")  # margine, non 1000


@pytest.mark.asyncio
async def test_global_view_exposes_drawdown_guardrail_block(db) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await PnlRepository(session).upsert_portfolio(
            USER,
            total_equity_usd=Decimal("600"),
            initial_equity_usd=Decimal("750"),
            peak_equity_usd=Decimal("760"),
            drawdown_pct=Decimal("20.86"),
            daily_loss_limit_used_pct=Decimal("0"),
            agent_status="running",
        )
        await session.commit()

    async with factory() as session:
        view = await ViewService(
            session,
            drawdown_cap_pct=-15.0,
            daily_loss_limit_pct=-8.0,
            min_portfolio_value_usd=5.0,
        ).global_view(USER)

    assert view.risk_guardrail is not None
    assert view.risk_guardrail.blocked is True
    assert view.risk_guardrail.reason == "drawdown_cap_guard"
    assert view.risk_guardrail.drawdown_pct == Decimal("20.86")


@pytest.mark.asyncio
async def test_spot_and_perp_views_return_open_positions(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await SpotPositionRepository(session).save(
            SpotPosition(
                position_id="sp1",
                user_id=USER,
                asset="BNB",
                size=Decimal("1"),
                entry_price=Decimal("600"),
                current_price=Decimal("620"),
                pnl_unrealized=Decimal("20"),
                opened_at=now,
                updated_at=now,
            )
        )
    async with factory() as session:
        spot = await ViewService(session).spot_view(USER)
        assert len(spot.open_positions) == 1
        assert spot.unrealized_pnl_usd == Decimal("20")
        perp = await ViewService(session).perp_view(USER)
        assert perp.open_positions == []


@pytest.mark.asyncio
async def test_spot_and_perp_views_share_bot_active_days(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    first_order_at = now - timedelta(days=3)
    async with factory() as session:
        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id="spot_first_order",
                user_id=USER,
                asset="BNB",
                side="buy",
                amount=Decimal("0.1"),
                price=Decimal("600"),
                amount_quote=Decimal("60"),
                status="prepared",
                timestamp_utc=first_order_at,
            )
        )
        await PerpTradeRepository(session).save(
            PerpTrade(
                trade_id="perp_close_today",
                user_id=USER,
                asset="ETH",
                side="long",
                direction="close",
                size=Decimal("0.1"),
                price=Decimal("3000"),
                leverage=25,
                status="confirmed",
                timestamp_utc=now,
                pnl_usd=Decimal("2.5"),
            )
        )

    async with factory() as session:
        service = ViewService(session)
        spot = await service.spot_view(USER)
        perp = await service.perp_view(USER)

    assert spot.bot_active_days == 4
    assert perp.bot_active_days == 4
    assert spot.trade_count_today == 0
    assert perp.trade_count_today == 1


@pytest.mark.asyncio
async def test_perp_history_uses_position_entry_for_partial_closes(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await PerpPositionRepository(session).save(
            PerpPosition(
                position_id="pos_eth_tp1",
                open_trade_id="dry_eth_open",
                user_id=USER,
                asset="ETH",
                side="long",
                size=Decimal("0.3"),
                entry_price=Decimal("1557.74"),
                current_price=Decimal("1572.00"),
                leverage=25,
                pnl_unrealized=Decimal("0"),
                tp1_reached=True,
                status="closed",
                opened_at=now,
                updated_at=now,
            )
        )
        repo = PerpTradeRepository(session)
        await repo.save(
            PerpTrade(
                trade_id="dry_eth_open",
                user_id=USER,
                asset="ETH",
                side="long",
                direction="open",
                size=Decimal("1.0"),
                price=Decimal("1557.74"),
                leverage=25,
                status="prepared",
                timestamp_utc=now,
            )
        )
        await repo.save(
            PerpTrade(
                trade_id="cls_pos_eth_tp1_aaaa1111",
                user_id=USER,
                asset="ETH",
                side="long",
                direction="close",
                size=Decimal("0.7"),
                price=Decimal("1572.36"),
                leverage=25,
                status="confirmed",
                timestamp_utc=now,
                notes="auto_close:take_profit_1_partial",
                pnl_usd=Decimal("9.50"),
            )
        )
        await repo.save(
            PerpTrade(
                trade_id="cls_pos_eth_tp1_bbbb2222",
                user_id=USER,
                asset="ETH",
                side="long",
                direction="close",
                size=Decimal("0.3"),
                price=Decimal("1571.90"),
                leverage=25,
                status="confirmed",
                timestamp_utc=now,
                notes="auto_close:trailing_stop",
                pnl_usd=Decimal("3.25"),
            )
        )
    async with factory() as session:
        view = await ViewService(session).perp_view(USER)
        eth_history = [trade for trade in view.history if trade.asset == "ETH"]
        assert len(eth_history) == 2
        assert {trade.entry_price for trade in eth_history} == {Decimal("1557.74")}


@pytest.mark.asyncio
async def test_archive_dry_run_records_copies_and_clears_live_data(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id="dry_spot_1",
                user_id=USER,
                asset="BNB",
                side="buy",
                amount=Decimal("0.1"),
                price=Decimal("600"),
                amount_quote=Decimal("60"),
                status="prepared",
                provider="dry_run",
                timestamp_utc=now,
            )
        )
        await AgentDecisionRepository(session).save(
            AgentDecision(
                decision_id="dry_dec_1",
                user_id=USER,
                timestamp_utc=now,
                asset="BNB",
                market="spot",
                action="approve",
                reasoning="dry_run regression",
                trade_id="dry_spot_1",
            )
        )
        await PnlRepository(session).save_snapshot(
            PnlSnapshot(user_id=USER, timestamp_utc=now, total_equity_usd=Decimal("500"))
        )
        await PnlRepository(session).upsert_portfolio(
            USER,
            total_equity_usd=Decimal("612"),
            initial_equity_usd=Decimal("500"),
            peak_equity_usd=Decimal("650"),
            drawdown_pct=Decimal("-5"),
            max_drawdown_pct=Decimal("-8"),
            exposure_pct=Decimal("20"),
            daily_pnl_usd=Decimal("12"),
            trades_today=3,
        )
        await session.commit()

    async with factory() as session:
        archive = await archive_dry_run_records(
            session,
            user_id=USER,
            archive_label="test_archive",
            reset_portfolio_capital_usd=Decimal("500"),
        )
        runs = await list_archived_runs(session, user_id=USER)
        remaining_trades = await SpotTradeRepository(session).list_for_user(USER)
        remaining_decisions = await AgentDecisionRepository(session).recent_for_user(USER)
        remaining_snapshots = await PnlRepository(session).recent_for_user(USER)
        portfolio = await PnlRepository(session).get_portfolio(USER)

    assert archive.archive_label == "test_archive"
    assert runs[0]["counts"]["spot_trades"] == 1
    assert runs[0]["counts"]["agent_decisions"] == 1
    assert runs[0]["counts"]["pnl_snapshots"] == 1
    assert runs[0]["counts"]["portfolio_state"] == 1
    assert remaining_trades == []
    assert remaining_decisions == []
    assert remaining_snapshots == []
    assert portfolio is not None
    assert portfolio.total_equity_usd == Decimal("500")
    assert portfolio.trades_today == 0


@pytest.mark.asyncio
async def test_reset_all_data_wipes_everything_and_optionally_backs_up(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id="t1", user_id=USER, asset="BNB", side="buy",
                amount=Decimal("0.1"), price=Decimal("600"), amount_quote=Decimal("60"),
                status="prepared", provider="dry_run", timestamp_utc=now,
            )
        )
        await PerpPositionRepository(session).save(
            PerpPosition(
                position_id="pp1", user_id=USER, asset="DOGE", side="long",
                size=Decimal("1"), entry_price=Decimal("0.07"), current_price=Decimal("0.07"),
                leverage=10, opened_at=now, updated_at=now,
            )
        )
        await PnlRepository(session).save_snapshot(
            PnlSnapshot(user_id=USER, timestamp_utc=now, total_equity_usd=Decimal("500"))
        )
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("612"), initial_equity_usd=Decimal("500"),
            peak_equity_usd=Decimal("650"), drawdown_pct=Decimal("20.86"),
            max_drawdown_pct=Decimal("20.86"), daily_loss_limit_used_pct=Decimal("-9"),
            exposure_pct=Decimal("12.5"), agent_status="running", trades_today=3,
        )
        await session.commit()

    async with factory() as session:
        result = await reset_all_data(
            session,
            user_id=USER,
            backup_label="snap_2026",
            reset_portfolio_capital_usd=Decimal("500"),
        )
        runs = await list_archived_runs(session, user_id=USER)
        trades = await SpotTradeRepository(session).list_for_user(USER)
        perps = await PerpPositionRepository(session).open_for_user(USER)
        snapshots = await PnlRepository(session).recent_for_user(USER)
        portfolio = await PnlRepository(session).get_portfolio(USER)
        view = await ViewService(
            session,
            drawdown_cap_pct=-15.0,
            daily_loss_limit_pct=-8.0,
            min_portfolio_value_usd=5.0,
        ).global_view(USER)

    # Backup salvato con i conteggi corretti.
    assert result["archived_run_id"] is not None
    assert result["backup_label"] == "snap_2026"
    assert result["deleted"]["spot_trades"] == 1
    assert result["deleted"]["perp_positions"] == 1
    assert result["portfolio_reset"] is True
    assert result["reset_portfolio_capital_usd"] == "500"
    assert runs[0]["archive_label"] == "snap_2026"
    # Tutto azzerato.
    assert trades == []
    assert perps == []
    assert snapshots == []
    assert portfolio is not None
    assert portfolio.total_equity_usd == Decimal("500")
    assert portfolio.initial_equity_usd == Decimal("500")
    assert portfolio.peak_equity_usd == Decimal("500")
    assert portfolio.drawdown_pct == Decimal("0")
    assert portfolio.max_drawdown_pct == Decimal("0")
    assert portfolio.daily_loss_limit_used_pct == Decimal("0")
    assert portfolio.trades_today == 0
    assert portfolio.agent_status == "idle"
    assert view.risk_guardrail is not None
    assert view.risk_guardrail.blocked is False


@pytest.mark.asyncio
async def test_adjust_equity_deposit_raises_base_not_pnl(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("250"), initial_equity_usd=Decimal("200"),
            peak_equity_usd=Decimal("260"),
        )
        await session.commit()

    async with factory() as session:
        portfolio, adj = await PnlRepository(session).adjust_equity(
            USER, amount=Decimal("200"), base_capital=Decimal("200"), note="versamento test", now=now,
        )

    # Equity e base salgono di 200; il PnL implicito (total - initial) resta 50.
    assert portfolio.total_equity_usd == Decimal("450")
    assert portfolio.initial_equity_usd == Decimal("400")
    assert portfolio.total_equity_usd - portfolio.initial_equity_usd == Decimal("50")
    assert portfolio.peak_equity_usd == Decimal("460")  # 260 + 200
    assert adj.amount == Decimal("200")
    assert adj.balance_after == Decimal("450")


@pytest.mark.asyncio
async def test_adjust_equity_withdrawal_and_negative_guard(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("300"), initial_equity_usd=Decimal("300"),
            peak_equity_usd=Decimal("300"),
        )
        await session.commit()

    async with factory() as session:
        repo = PnlRepository(session)
        portfolio, _ = await repo.adjust_equity(
            USER, amount=Decimal("-50"), base_capital=Decimal("200"), note=None, now=now,
        )
        assert portfolio.total_equity_usd == Decimal("250")
        assert portfolio.initial_equity_usd == Decimal("250")

    async with factory() as session:
        with pytest.raises(ValueError):
            await PnlRepository(session).adjust_equity(
                USER, amount=Decimal("-9999"), base_capital=Decimal("200"), note=None, now=now,
            )


@pytest.mark.asyncio
async def test_adjust_equity_initialises_missing_portfolio(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        portfolio, _ = await PnlRepository(session).adjust_equity(
            USER, amount=Decimal("100"), base_capital=Decimal("200"), note=None, now=now,
        )
    # Nessun portfolio preesistente: parte dal capitale base (200) + 100.
    assert portfolio.total_equity_usd == Decimal("300")
    assert portfolio.initial_equity_usd == Decimal("300")


def test_equity_curve_deposits_up_to_is_time_weighted() -> None:
    """Un versamento non deve rebaselinare la storia: il capitale versato cresce
    solo dal momento del deposito in poi (somma cumulativa fino a t)."""
    from datetime import timedelta
    from types import SimpleNamespace

    from backend.app.api.routes.views import _deposits_up_to

    t0 = datetime(2026, 6, 26, 10, 0, tzinfo=UTC)
    adjustments = [
        SimpleNamespace(amount=Decimal("200"), created_at=t0),
        SimpleNamespace(amount=Decimal("-50"), created_at=t0 + timedelta(hours=2)),
        SimpleNamespace(amount=Decimal("550"), created_at=t0 + timedelta(hours=5)),
    ]
    assert _deposits_up_to(adjustments, t0 - timedelta(hours=1)) == Decimal("0")   # prima di tutto
    assert _deposits_up_to(adjustments, t0 + timedelta(hours=1)) == Decimal("200")  # dopo il 1°
    assert _deposits_up_to(adjustments, t0 + timedelta(hours=3)) == Decimal("150")  # dopo +200 e -50
    assert _deposits_up_to(adjustments, t0 + timedelta(hours=6)) == Decimal("700")  # dopo tutti

    # Ricostruzione baseline: initial (post-versamenti) - totale = base pre-versamenti.
    initial_post = Decimal("900")   # es. 200 base + 700 versamenti netti
    total = _deposits_up_to(adjustments, t0 + timedelta(hours=6))
    base_initial = initial_post - total
    assert base_initial == Decimal("200")
    # Punto storico prima dei versamenti: contributed = base (storia invariata).
    contributed_old = base_initial + _deposits_up_to(adjustments, t0 - timedelta(hours=1))
    assert contributed_old == Decimal("200")


@pytest.mark.asyncio
async def test_reset_all_data_without_backup_does_not_archive(db) -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id="t2", user_id=USER, asset="BNB", side="buy",
                amount=Decimal("0.1"), price=Decimal("600"), amount_quote=Decimal("60"),
                status="prepared", provider="dry_run", timestamp_utc=now,
            )
        )
        await session.commit()

    async with factory() as session:
        result = await reset_all_data(session, user_id=USER, backup_label=None)
        runs = await list_archived_runs(session, user_id=USER)
        trades = await SpotTradeRepository(session).list_for_user(USER)

    assert result["archived_run_id"] is None
    assert result["portfolio_reset"] is False
    assert result["reset_portfolio_capital_usd"] is None
    assert runs == []
    assert trades == []


def test_backup_creates_timestamped_copy_and_prunes(tmp_path: Path) -> None:
    src = tmp_path / "local.db"
    src.write_bytes(b"SQLite format 3\x00stub")
    url = f"sqlite+aiosqlite:///{src}"
    backup_dir = tmp_path / "backups"

    created = backup_db(url, backup_dir, retention_days=7)
    assert created is not None
    assert created.exists()
    assert created.parent == backup_dir

    # An old backup gets pruned.
    old = backup_dir / "local_20000101T000000Z.db"
    old.write_bytes(b"old")
    import os

    old_time = datetime.now(UTC).timestamp() - 30 * 86_400
    os.utime(old, (old_time, old_time))
    backup_db(url, backup_dir, retention_days=7)
    assert not old.exists()


def test_backup_returns_none_for_missing_db(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'does_not_exist.db'}"
    assert backup_db(url, tmp_path / "backups") is None
