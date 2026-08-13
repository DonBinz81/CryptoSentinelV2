"""Global manual perpetual execution-provider selector with no automatic fallback.

Same pattern as the spot registry ([registry.py](backend/app/execution/registry.py)):
Settings provide the boot default, a persisted RuntimeState selection overrides
it, and switching is an explicit admin-only action.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.execution.network_selection import effective_execution_settings
from backend.app.execution.perp_base import (
    PerpExecutionProvider,
    PerpExecutionProviderName,
    PerpProviderStatus,
)
from backend.app.execution.perp_providers import BnbSdkPerpProvider
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

logger = get_logger("execution.perp_registry")

_PROVIDER_STATE_KEY = "perp_execution_provider"


class PerpExecutionRegistry:
    """Own perp provider instances and expose one global active provider."""

    def __init__(
        self,
        settings: Settings,
        providers: dict[PerpExecutionProviderName, PerpExecutionProvider] | None = None,
    ) -> None:
        settings = effective_execution_settings(settings)
        self.settings = settings
        self._providers = providers or {
            PerpExecutionProviderName.BNB_SDK: BnbSdkPerpProvider(settings),
        }
        self._user_id = str(settings.default_user_id)
        self._active = self._load_active(settings)

    def _load_active(self, settings: Settings) -> PerpExecutionProviderName:
        """Boot default from Settings, overridden by a persisted selection."""

        persisted = get_runtime_value(self._user_id, _PROVIDER_STATE_KEY)
        if persisted:
            try:
                candidate = PerpExecutionProviderName(persisted)
                if candidate in self._providers:
                    return candidate
            except ValueError:
                pass
        return PerpExecutionProviderName(settings.perp_execution_provider)

    @property
    def active_name(self) -> PerpExecutionProviderName:
        return self._active

    @property
    def active(self) -> PerpExecutionProvider:
        return self._providers[self._active]

    def select(self, provider: PerpExecutionProviderName) -> PerpProviderStatus:
        """Apply an explicit global selection; never fall back automatically."""

        if provider not in self._providers:
            raise ValueError(f"Unsupported perp execution provider: {provider}")
        self._active = provider
        set_runtime_value(self._user_id, _PROVIDER_STATE_KEY, provider.value)
        logger.info("perp_execution_provider_selected", provider=provider.value)
        return self.active.status()

    def statuses(self) -> list[PerpProviderStatus]:
        return [provider.status() for provider in self._providers.values()]


@lru_cache
def get_perp_execution_registry() -> PerpExecutionRegistry:
    """Return the process-wide perp execution-provider selector."""

    return PerpExecutionRegistry(get_settings())
