"""Perpetual V2 order-flow delta signal namespace."""

from backend.app.agent.signals.base import SignalModule, SignalPayload, SignalResult


class OrderflowDeltaSignal(SignalModule[SignalPayload, SignalResult]):
    """Placeholder for Binance Futures aggTrade delta aggregation."""

    name = "perp_orderflow_delta_v2"

    async def evaluate(self, payload: SignalPayload) -> SignalResult:
        raise NotImplementedError("Order-flow delta is reserved for V2.")
