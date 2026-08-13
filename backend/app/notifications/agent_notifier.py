"""Sistema di notifiche push per eventi dell'agente autonomo."""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from uuid import UUID

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.notifications.fcm.token_store import DeviceTokenStore
from backend.app.notifications.service import get_notification_service
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value
from backend.app.schemas.notification_prefs import NotificationPreferences

logger = get_logger("notifications.agent_notifier")

_MAX_NOTIFIED_IDS = 500


class AgentNotifier:
    """Notifiche push tipizzate per trade, rischio e riepilogo giornaliero."""

    PREFS_KEY = "notification_preferences"
    NOTIFIED_TRADES_KEY = "notified_trade_ids"
    RISK_STATE_KEY = "last_risk_notification"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._store = DeviceTokenStore(settings.fcm_token_store_path)

    # ------------------------------------------------------------------
    # Preferenze utente
    # ------------------------------------------------------------------

    def get_preferences(self, user_id: str) -> NotificationPreferences:
        """Legge da RuntimeState; fallback a default (tutto True)."""
        raw = get_runtime_value(user_id, self.PREFS_KEY)
        if raw:
            try:
                data = json.loads(raw)
                return NotificationPreferences(**data)
            except Exception:
                pass
        return NotificationPreferences()

    def set_preferences(self, user_id: str, prefs: NotificationPreferences) -> None:
        """Persiste in RuntimeState."""
        set_runtime_value(user_id, self.PREFS_KEY, json.dumps(prefs.model_dump()))

    # ------------------------------------------------------------------
    # Notifiche trade
    # ------------------------------------------------------------------

    async def notify_trade_opened(
        self,
        user_id: str,
        trade_id: str,
        asset: str,
        market: str,
        direction: str,
        entry_price: Decimal,
        size_usd: Decimal,
        stop_loss: Decimal | None,
        is_dry_run: bool,
    ) -> bool:
        """Invia notifica apertura trade. Idempotente: salva trade_id in RuntimeState."""
        prefs = self.get_preferences(user_id)
        pref_key = "spot_trades" if market == "spot" else "perp_trades"
        if not getattr(prefs, pref_key, True):
            return False
        if is_dry_run and not self.settings.notify_dry_run_trades:
            return False
        if self._is_already_notified(user_id, trade_id):
            return False

        topic = (
            self.settings.fcm_spot_topic if market == "spot" else self.settings.fcm_perp_topic
        )
        dry_label = " [DRY]" if is_dry_run else ""
        sl_text = f" | SL {stop_loss:.4f}" if stop_loss else ""
        title = f"Trade aperto: {asset.upper()} {market.upper()}{dry_label}"
        body = (
            f"{direction.upper()} @ {entry_price:.4f} | Size ${size_usd:.2f}{sl_text}"
        )
        sent = await self._send(
            user_id=user_id,
            title=title,
            body=body,
            severity="critical",
            data={
                "topic": topic,
                "trade_id": trade_id,
                "asset": asset,
                "market": market,
                "direction": direction,
                "entry_price": str(entry_price),
                "size_usd": str(size_usd),
                "dry_run": str(is_dry_run).lower(),
            },
        )
        if sent:
            self._add_notified(user_id, trade_id)
        return sent

    async def notify_trade_closed(
        self,
        user_id: str,
        trade_id: str,
        asset: str,
        market: str,
        pnl_usd: Decimal,
        pnl_pct: Decimal,
        close_reason: str,
        is_dry_run: bool = False,
    ) -> bool:
        """Push ad alta priorità per chiusura posizione con PnL."""
        prefs = self.get_preferences(user_id)
        pref_key = "spot_trades" if market == "spot" else "perp_trades"
        if not getattr(prefs, pref_key, True):
            return False
        if is_dry_run and not self.settings.notify_dry_run_trades:
            return False

        topic = (
            self.settings.fcm_spot_topic if market == "spot" else self.settings.fcm_perp_topic
        )
        pnl_sign = "+" if pnl_usd >= 0 else ""
        title = f"Posizione chiusa: {asset.upper()} {market.upper()}"
        body = f"PnL {pnl_sign}{pnl_usd:.2f}$ ({pnl_sign}{pnl_pct:.2f}%) | {close_reason}"
        return await self._send(
            user_id=user_id,
            title=title,
            body=body,
            severity="critical",
            data={
                "topic": topic,
                "trade_id": trade_id,
                "asset": asset,
                "market": market,
                "pnl_usd": str(pnl_usd),
                "pnl_pct": str(pnl_pct),
                "close_reason": close_reason,
            },
        )

    # ------------------------------------------------------------------
    # Allarmi rischio
    # ------------------------------------------------------------------

    async def notify_risk_alert(
        self,
        user_id: str,
        alert_type: str,
        detail: str,
    ) -> bool:
        """Notifica allarme rischio con anti-spam (no ri-invio se stesso stato)."""
        prefs = self.get_preferences(user_id)
        if not prefs.risk_alerts:
            return False

        # Anti-spam: non inviare se stesso alert_type + detail già notificato
        last_raw = get_runtime_value(user_id, self.RISK_STATE_KEY)
        current_state = json.dumps({"alert_type": alert_type, "detail": detail})
        if last_raw == current_state:
            return False

        title = f"Allarme rischio: {alert_type.replace('_', ' ').title()}"
        body = detail
        sent = await self._send(
            user_id=user_id,
            title=title,
            body=body,
            severity="critical",
            data={
                "topic": self.settings.fcm_risk_topic,
                "alert_type": alert_type,
                "detail": detail,
            },
        )
        if sent:
            set_runtime_value(user_id, self.RISK_STATE_KEY, current_state)
        return sent

    # ------------------------------------------------------------------
    # Riepilogo giornaliero
    # ------------------------------------------------------------------

    async def notify_daily_summary(
        self,
        user_id: str,
        spot_trades: int,
        perp_trades: int,
        daily_pnl_usd: Decimal,
        win_rate_pct: float,
    ) -> bool:
        """Riepilogo giornaliero aggregato."""
        prefs = self.get_preferences(user_id)
        if not prefs.daily_summary:
            return False

        pnl_sign = "+" if daily_pnl_usd >= 0 else ""
        title = "Riepilogo giornaliero CryptoSentinel"
        body = (
            f"Spot {spot_trades} | Perp {perp_trades} | "
            f"PnL {pnl_sign}{daily_pnl_usd:.2f}$ | WR {win_rate_pct:.1f}%"
        )
        return await self._send(
            user_id=user_id,
            title=title,
            body=body,
            severity="normal",
            data={
                "topic": self.settings.fcm_summary_topic,
                "spot_trades": str(spot_trades),
                "perp_trades": str(perp_trades),
                "daily_pnl_usd": str(daily_pnl_usd),
                "win_rate_pct": str(win_rate_pct),
            },
        )

    # ------------------------------------------------------------------
    # Evento critico agente
    # ------------------------------------------------------------------

    async def notify_agent_critical(
        self,
        user_id: str,
        event: str,
        detail: str,
    ) -> bool:
        """Evento critico (degraded, servizio giù)."""
        prefs = self.get_preferences(user_id)
        if not prefs.critical:
            return False

        title = f"Agente critico: {event}"
        body = detail
        return await self._send(
            user_id=user_id,
            title=title,
            body=body,
            severity="critical",
            data={
                "topic": self.settings.fcm_critical_topic or "cryptosentinel-critical",
                "event": event,
                "detail": detail,
            },
        )

    # ------------------------------------------------------------------
    # Idempotenza trade
    # ------------------------------------------------------------------

    def _get_notified_set(self, user_id: str) -> set[str]:
        """Carica set trade_id già notificati da RuntimeState."""
        raw = get_runtime_value(user_id, self.NOTIFIED_TRADES_KEY)
        if raw:
            try:
                return set(json.loads(raw))
            except Exception:
                pass
        return set()

    def _is_already_notified(self, user_id: str, trade_id: str) -> bool:
        return trade_id in self._get_notified_set(user_id)

    def _add_notified(self, user_id: str, trade_id: str) -> None:
        """Aggiunge trade_id al set; mantiene massimo 500 entries (sliding window FIFO)."""
        raw = get_runtime_value(user_id, self.NOTIFIED_TRADES_KEY)
        current_list: list[str] = []
        if raw:
            try:
                current_list = json.loads(raw)
            except Exception:
                current_list = []
        if trade_id not in current_list:
            current_list.append(trade_id)
        # Tronca a _MAX_NOTIFIED_IDS mantenendo gli ultimi
        if len(current_list) > _MAX_NOTIFIED_IDS:
            current_list = current_list[-_MAX_NOTIFIED_IDS:]
        set_runtime_value(user_id, self.NOTIFIED_TRADES_KEY, json.dumps(current_list))

    # ------------------------------------------------------------------
    # Invio FCM
    # ------------------------------------------------------------------

    async def _send(
        self,
        user_id: str,
        title: str,
        body: str,
        severity: str,
        data: dict[str, str],
    ) -> bool:
        """Invia a tutti i token FCM dell'utente. Ritorna True se almeno uno inviato."""
        if not self.settings.fcm_enabled:
            logger.debug("fcm_disabled_skip", title=title, user_id=user_id)
            return False
        try:
            tokens = self._store.tokens_for_user(UUID(user_id))
        except Exception as exc:
            logger.warning("agent_notifier_token_fetch_failed", error=str(exc))
            return False
        if not tokens:
            logger.debug("no_fcm_tokens", user_id=user_id)
            return False

        svc = get_notification_service()
        try:
            result = svc.fcm.send(
                tokens=tokens,
                title=title,
                body=body,
                severity=severity,  # type: ignore[arg-type]
                data={k: str(v) for k, v in data.items()},
            )
            sent = result.success_count > 0
            logger.info(
                "agent_notifier_sent",
                title=title,
                user_id=user_id,
                success=result.success_count,
                failure=result.failure_count,
                status=result.status,
            )
            return sent
        except Exception as exc:
            logger.warning("agent_notifier_send_failed", error=str(exc), title=title)
            return False


@lru_cache
def get_agent_notifier() -> AgentNotifier:
    """Singleton cached dell'AgentNotifier."""
    return AgentNotifier(get_settings())
