"""Global manual execution-provider selector with no automatic fallback.

Same pattern as the market-data registry (Step 3): Settings provide the boot
default, a persisted RuntimeState selection overrides it, and switching is an
explicit admin-only action. No automatic fallback between providers.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.execution.network_selection import effective_execution_settings
from backend.app.execution.base import (
    ExecutionProvider,
    ExecutionProviderName,
    ExecutionProviderStatus,
)
from backend.app.execution.providers import PancakeSwapProvider, TWAKProvider
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

logger = get_logger("execution.registry")

_PROVIDER_STATE_KEY = "execution_provider"


class ExecutionProviderRegistry:
    """Own provider instances and expose one global active execution provider."""

    def __init__(
        self,
        settings: Settings,
        providers: dict[ExecutionProviderName, ExecutionProvider] | None = None,
    ) -> None:
        settings = effective_execution_settings(settings)
        self.settings = settings
        self._providers = providers or {
            ExecutionProviderName.TWAK: TWAKProvider(settings),
            ExecutionProviderName.PANCAKESWAP: PancakeSwapProvider(settings),
        }
        self._user_id = str(settings.default_user_id)
        self._active = self._load_active(settings)

    def _load_active(self, settings: Settings) -> ExecutionProviderName:
        """Boot default from Settings, overridden by a persisted selection."""

        persisted = get_runtime_value(self._user_id, _PROVIDER_STATE_KEY)
        if persisted:
            try:
                candidate = ExecutionProviderName(persisted)
                if candidate in self._providers:
                    return candidate
            except ValueError:
                pass
        return ExecutionProviderName(settings.execution_provider)

    @property
    def active_name(self) -> ExecutionProviderName:
        return self._active

    @property
    def active(self) -> ExecutionProvider:
        return self._providers[self._active]

    def select(self, provider: ExecutionProviderName) -> ExecutionProviderStatus:
        """Apply an explicit global selection; never fall back automatically."""

        if provider not in self._providers:
            raise ValueError(f"Unsupported execution provider: {provider}")
        self._active = provider
        set_runtime_value(self._user_id, _PROVIDER_STATE_KEY, provider.value)
        logger.info("execution_provider_selected", provider=provider.value)
        return self.active.status()

    def statuses(self) -> list[ExecutionProviderStatus]:
        return [provider.status() for provider in self._providers.values()]


@lru_cache
def get_execution_provider_registry() -> ExecutionProviderRegistry:
    """Return the process-wide execution-provider selector."""

    return ExecutionProviderRegistry(get_settings())
