"""Signal engine interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class SignalModule(ABC, Generic[InputT, OutputT]):
    """Base contract for independent signal modules with fallback support."""

    name: str

    @abstractmethod
    async def evaluate(self, payload: InputT) -> OutputT:
        """Evaluate a signal from a normalized payload."""


class SignalUnavailable(RuntimeError):
    """Raised when a signal source is unavailable and a fallback should be used."""


SignalPayload = dict[str, Any]
SignalResult = dict[str, Any]
