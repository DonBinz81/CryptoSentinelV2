"""Execution-layer status and competition checks."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep
from backend.app.execution.perp_registry import (
    PerpExecutionRegistry,
    get_perp_execution_registry,
)
from backend.app.execution.registry import (
    ExecutionProviderRegistry,
    get_execution_provider_registry,
)
from backend.app.execution.service import ExecutionService, get_execution_service
from backend.app.schemas.execution import (
    ExecutionProviderSelectionRequest,
    ExecutionProviderSelectionResponse,
    ExecutionNetworkSelectionRequest,
    ExecutionWalletsResponse,
    ExecutionWalletSelectionRequest,
    PerpProviderSelectionRequest,
    PerpProviderSelectionResponse,
    RpcEndpointSelectionRequest,
)

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])
ExecutionServiceDep = Annotated[ExecutionService, Depends(get_execution_service)]
RegistryDep = Annotated[ExecutionProviderRegistry, Depends(get_execution_provider_registry)]
PerpRegistryDep = Annotated[PerpExecutionRegistry, Depends(get_perp_execution_registry)]


@router.get("/status")
async def execution_status(
    service: ExecutionServiceDep,
    _: ReadAccessDep,
) -> dict[str, Any]:
    """Return non-sensitive execution readiness."""

    return service.status()


@router.get("/wallets", response_model=ExecutionWalletsResponse)
async def execution_wallets(
    service: ExecutionServiceDep,
    _: ReadAccessDep,
) -> ExecutionWalletsResponse:
    """Return non-sensitive execution wallets and live BNB balances."""

    return await service.wallets()


@router.get("/provider", response_model=ExecutionProviderSelectionResponse)
async def execution_provider_status(
    registry: RegistryDep,
    _: ReadAccessDep,
) -> ExecutionProviderSelectionResponse:
    """Return the global spot execution provider selection and diagnostics."""

    return ExecutionProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
    )


@router.put("/provider", response_model=ExecutionProviderSelectionResponse)
async def select_execution_provider(
    request: ExecutionProviderSelectionRequest,
    registry: RegistryDep,
    _: AdminAccessDep,
) -> ExecutionProviderSelectionResponse:
    """Select one global spot execution provider until restart. No fallback."""

    registry.select(request.provider)
    return ExecutionProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
    )


@router.get("/perp-provider", response_model=PerpProviderSelectionResponse)
async def perp_provider_status(
    registry: PerpRegistryDep,
    _: ReadAccessDep,
) -> PerpProviderSelectionResponse:
    """Return the global perp execution provider selection and diagnostics."""

    return PerpProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
    )


@router.put("/perp-provider", response_model=PerpProviderSelectionResponse)
async def select_perp_provider(
    request: PerpProviderSelectionRequest,
    registry: PerpRegistryDep,
    _: AdminAccessDep,
) -> PerpProviderSelectionResponse:
    """Select one global perp execution provider until restart. No fallback."""

    registry.select(request.provider)
    return PerpProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
    )


@router.put("/network", response_model=ExecutionWalletsResponse)
async def select_execution_network(
    request: ExecutionNetworkSelectionRequest,
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> ExecutionWalletsResponse:
    """Select the BSC network used by execution diagnostics and new providers."""

    get_execution_provider_registry.cache_clear()
    get_perp_execution_registry.cache_clear()
    return await service.select_network(request.network)


@router.put("/wallet", response_model=ExecutionWalletsResponse)
async def select_execution_wallet(
    request: ExecutionWalletSelectionRequest,
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> ExecutionWalletsResponse:
    """Select the public wallet address used by execution diagnostics and requests."""

    try:
        return await service.select_wallet(request.address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wallets", response_model=ExecutionWalletsResponse)
async def add_execution_wallet(
    request: ExecutionWalletSelectionRequest,
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> ExecutionWalletsResponse:
    """Add a public wallet address to the runtime wallet list and select it."""

    try:
        return await service.add_wallet(request.address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/rpc-endpoint", response_model=ExecutionWalletsResponse)
async def select_rpc_endpoint(
    request: RpcEndpointSelectionRequest,
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> ExecutionWalletsResponse:
    """Force the preferred BSC RPC endpoint for subsequent execution attempts."""

    try:
        return await service.select_rpc_endpoint(request.index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class TokenSendRequest(BaseModel):
    to_address: str
    amount: str
    token: str
    wallet_password: str


@router.post("/send")
async def send_token(
    request: TokenSendRequest,
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> dict[str, Any]:
    """Invia token o BNB nativi a un indirizzo tramite TWAK CLI."""
    return await service.send_token(
        to_address=request.to_address,
        amount=request.amount,
        token=request.token,
        wallet_password=request.wallet_password,
    )


@router.get("/competition/status")
async def competition_status(
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> dict[str, Any]:
    """Verify competition registration directly against the configured contract."""

    return await service.competition_registration_status()
