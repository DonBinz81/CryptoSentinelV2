"""Spot V2 relative strength signal namespace."""

from backend.app.agent.signals.base import SignalModule, SignalPayload, SignalResult


class RelativeStrengthSignal(SignalModule[SignalPayload, SignalResult]):
    """Placeholder for V2 token outperformance ranking."""

    name = "spot_relative_strength_v2"

    async def evaluate(self, payload: SignalPayload) -> SignalResult:
        raise NotImplementedError("Relative strength is reserved for V2.")
