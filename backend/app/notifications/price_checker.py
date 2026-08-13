"""Background task: fetches prices every minute and fires FCM when alerts trigger."""

from __future__ import annotations

import asyncio
import time

from backend.app.core.logging import get_logger
from backend.app.data.market_data.base import ProviderError
from backend.app.data.market_data.registry import (
    MarketDataRegistry,
    get_alert_market_data_registry,
)
from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID
from backend.app.notifications.alert_store import AlertStore, get_alert_store
from backend.app.notifications.service import NotificationService, get_notification_service
from backend.app.schemas.alerts import AlertSyncRequest, PendingFavAlert

logger = get_logger("notifications.price_checker")

CHECK_INTERVAL_S = 60
RANGE_COOLDOWN_MS = 5 * 60 * 1000


def _fmt(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:.2f}"
    return f"{v:.6f}"


def _price_key(coin_id: str, direction: str, threshold: float) -> str:
    return f"{coin_id}:{direction}:{threshold}"


async def _fetch_prices(
    coin_ids: list[str],
    vs_currencies: list[str],
    registry: MarketDataRegistry | None = None,
) -> dict[str, dict[str, float]]:
    selected_registry = registry or get_alert_market_data_registry()
    try:
        quotes = await selected_registry.get_prices(coin_ids, vs_currencies)
        prices: dict[str, dict[str, float]] = {}
        for quote in quotes:
            prices.setdefault(quote.asset_id, {})[quote.currency] = quote.price
        return prices
    except ProviderError as exc:
        logger.warning(
            "market_data_fetch_failed",
            provider=selected_registry.active_name.value,
            error=str(exc),
        )
        return {}


def _config_coins_and_currencies(config: AlertSyncRequest) -> tuple[list[str], set[str]]:
    """Collect the coin ids and vs-currencies referenced by one config."""

    coin_ids: list[str] = []
    vs: set[str] = {"usd"}
    if config.fav_currency and config.fav_currency.lower() != "usd":
        vs.add(config.fav_currency.lower())
    for a in config.price_alerts:
        if a.coin_id not in coin_ids:
            coin_ids.append(a.coin_id)
    for a in config.range_alerts:
        if a.coin_id not in coin_ids:
            coin_ids.append(a.coin_id)
    has_fav = (config.fav_up_pct > 0 or config.fav_down_pct > 0) and bool(config.fav_coins)
    if has_fav:
        for c in config.fav_coins:
            if c.id not in coin_ids:
                coin_ids.append(c.id)
    return coin_ids, vs


async def run_price_check(registry: MarketDataRegistry | None = None) -> None:
    """Single price-check tick.

    Each registered device is evaluated against its OWN alert config and is
    notified only on its own token. Tokens without a device_id (registered by
    pre-separation app versions) fall back to the legacy global config.
    """

    svc = get_notification_service()
    pairs = svc.store.tokens_with_device(DEFAULT_SINGLE_USER_ID)
    if not pairs:
        logger.warning("price_check_no_devices", requested_count=0)
        return

    # Group tokens by device (None bucket = legacy tokens without a device_id).
    device_tokens: dict[str | None, list[str]] = {}
    for token, device_id in pairs:
        device_tokens.setdefault(device_id or None, []).append(token)

    # Load each device's config/store; collect the union of coins to fetch once.
    units: list[tuple[AlertStore, AlertSyncRequest, list[str]]] = []
    union_coins: list[str] = []
    union_vs: set[str] = {"usd"}
    for device_id, tokens in device_tokens.items():
        store = get_alert_store(device_id)
        config = store.get_config()
        if config is None:
            continue
        coin_ids, vs = _config_coins_and_currencies(config)
        if not coin_ids:
            continue
        units.append((store, config, tokens))
        union_vs |= vs
        for coin_id in coin_ids:
            if coin_id not in union_coins:
                union_coins.append(coin_id)

    if not units or not union_coins:
        return

    prices = await _fetch_prices(union_coins, list(union_vs), registry)
    if not prices:
        logger.warning(
            "price_check_no_prices",
            provider=(registry or get_alert_market_data_registry()).active_name.value,
            requested_count=len(union_coins),
        )
        return
    logger.info(
        "price_check_prices_loaded",
        provider=(registry or get_alert_market_data_registry()).active_name.value,
        device_count=len(units),
        requested_count=len(union_coins),
        returned_count=len(prices),
        missing_ids=[coin_id for coin_id in union_coins if coin_id not in prices],
    )

    for store, config, tokens in units:
        _evaluate_and_send(svc, store, config, tokens, prices)


def _evaluate_and_send(
    svc: NotificationService,
    store: AlertStore,
    config: AlertSyncRequest,
    tokens: list[str],
    prices: dict[str, dict[str, float]],
) -> None:
    """Evaluate one device's alerts against fetched prices and notify its tokens."""

    has_fav = (config.fav_up_pct > 0 or config.fav_down_pct > 0) and bool(config.fav_coins)
    state = store.get_state()
    now_ms = time.time() * 1000
    state_changed = False

    # --- Price alerts (one-shot) ---
    for alert in config.price_alerts:
        key = _price_key(alert.coin_id, alert.direction, alert.threshold)
        if key in state.triggered_keys and not alert.keep_active_after_trigger:
            continue
        price = prices.get(alert.coin_id, {}).get("usd", -1.0)
        if price < 0:
            continue
        previous_price = state.price_last_observed.get(key)
        if previous_price is None and alert.last_observed_price is not None:
            previous_price = alert.last_observed_price
        state.price_last_observed[key] = price
        state_changed = True

        cross_direction: str | None = None
        if alert.crossing_only:
            if previous_price is None or previous_price <= 0:
                continue
            rearm_percent = max(0.0, alert.rearm_percent)
            rearm_band = alert.threshold * (rearm_percent / 100.0)
            inside_rearm_band = alert.threshold - rearm_band <= price <= alert.threshold + rearm_band
            if key in state.price_waiting_rearm and rearm_percent > 0 and inside_rearm_band:
                continue
            if key in state.price_waiting_rearm:
                state.price_waiting_rearm.discard(key)
                continue
            crossed_up = previous_price < alert.threshold <= price
            crossed_down = previous_price > alert.threshold >= price
            if crossed_up:
                cross_direction = "up"
            elif crossed_down:
                cross_direction = "down"
            fire = cross_direction is not None
        else:
            fire = (alert.direction == "above" and price >= alert.threshold) or \
                   (alert.direction == "below" and price <= alert.threshold)
        if not fire:
            continue
        arrow = "▲" if alert.direction == "above" else "▼"
        label = "superato al rialzo" if alert.direction == "above" else "superato al ribasso"
        title = f"{arrow} {alert.coin_name} — soglia {label}"
        body = f"Soglia: ${_fmt(alert.threshold)}  ·  Prezzo: ${_fmt(price)}"
        if alert.note:
            body += f"\n📝 {alert.note}"
        effective_direction = alert.direction
        if cross_direction == "up":
            title = f"UP {alert.coin_name} - soglia superata al rialzo"
            effective_direction = "above"
        elif cross_direction == "down":
            title = f"DOWN {alert.coin_name} - soglia superata al ribasso"
            effective_direction = "below"
        svc.fcm.send(
            tokens=tokens, title=title, body=body, severity="critical",
            data={
                "type": "price_alert",
                "coin_id": alert.coin_id,
                "cross_direction": cross_direction or "",
            },
        )
        if alert.keep_active_after_trigger:
            if alert.crossing_only and alert.rearm_percent > 0:
                state.price_waiting_rearm.add(key)
            state.triggered_keys.discard(key)
        else:
            state.triggered_keys.add(key)
        state_changed = True
        logger.info("fcm_price_alert_fired", coin=alert.coin_id, direction=effective_direction, price=price)

    # --- Range alerts (repeating with cooldown) ---
    for alert in config.range_alerts:
        alert_id = f"{alert.coin_id}:{alert.min_price}:{alert.max_price}"
        price = prices.get(alert.coin_id, {}).get("usd", -1.0)
        if price < 0:
            continue
        is_inside = alert.min_price <= price <= alert.max_price
        was_inside = state.range_is_inside.get(alert_id)
        state.range_is_inside[alert_id] = is_inside
        if was_inside is None:
            state_changed = True
            continue
        if is_inside == was_inside:
            continue
        if now_ms - state.range_last_notified.get(alert_id, 0.0) < RANGE_COOLDOWN_MS:
            continue
        status_label = "↔ Entrato nel range" if is_inside else "↗ Uscito dal range"
        title = f"{status_label} — {alert.coin_name}"
        body = f"Range: ${_fmt(alert.min_price)} – ${_fmt(alert.max_price)}  ·  Ora: ${_fmt(price)}"
        if alert.note:
            body += f"\n📝 {alert.note}"
        svc.fcm.send(
            tokens=tokens, title=title, body=body, severity="critical",
            data={"type": "range_alert", "coin_id": alert.coin_id},
        )
        state.range_last_notified[alert_id] = now_ms
        state_changed = True
        logger.info("fcm_range_alert_fired", coin=alert.coin_id, inside=is_inside, price=price)

    # --- Fav coin move alerts ---
    if has_fav:
        fav_currency = config.fav_currency.lower()
        for coin in config.fav_coins:
            coin_prices = prices.get(coin.id, {})
            current = coin_prices.get(fav_currency, coin_prices.get("usd", -1.0))
            if current < 0:
                continue
            ref = state.fav_ref_prices.get(coin.id)
            if ref is None or ref <= 0:
                state.fav_ref_prices[coin.id] = current
                state_changed = True
                continue
            pct = (current - ref) / ref * 100.0
            direction: str | None = None
            if config.fav_up_pct > 0 and pct >= config.fav_up_pct:
                direction = "up"
            elif config.fav_down_pct > 0 and pct <= -config.fav_down_pct:
                direction = "down"
            if direction is None:
                continue
            arrow = "▲" if direction == "up" else "▼"
            label = "rialzo" if direction == "up" else "ribasso"
            title = f"{arrow} {coin.name} ({coin.symbol.upper()}) — {label} del {abs(pct):.1f}%"
            body = f"Movimento del {abs(pct):.1f}% verso il {label}  ·  Ora: ${_fmt(current)}"
            delivery = svc.fcm.send(
                tokens=tokens, title=title, body=body, severity="critical",
                data={
                    "type": "fav_alert",
                    "coin_id": coin.id,
                    "coin_name": coin.name,
                    "coin_symbol": coin.symbol,
                    "direction": direction,
                    "pct": f"{abs(pct):.8f}",
                    "current_price": f"{current:.12f}",
                    "ref_price": f"{ref:.12f}",
                },
            )
            if delivery.success_count > 0:
                state.pending_fav_alerts[coin.id] = PendingFavAlert(
                    coin_id=coin.id,
                    coin_name=coin.name,
                    coin_symbol=coin.symbol,
                    direction=direction,
                    pct=abs(pct),
                    current_price=current,
                    ref_price=ref,
                )
            state.fav_ref_prices[coin.id] = current
            state_changed = True
            logger.info("fcm_fav_alert_fired", coin=coin.id, direction=direction, pct=round(abs(pct), 2))

    if state_changed:
        store.update_state(state)


async def price_checker_loop() -> None:
    """Run price checks indefinitely every CHECK_INTERVAL_S seconds."""
    logger.info("price_checker_started", interval_s=CHECK_INTERVAL_S)
    while True:
        try:
            await run_price_check()
        except Exception as exc:
            logger.warning("price_checker_error", error=str(exc))
        await asyncio.sleep(CHECK_INTERVAL_S)
