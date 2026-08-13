"""API schemas for the execution-provider selectors (spot and perp)."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.execution.base import ExecutionProviderName, ExecutionProviderStatus
from backend.app.execution.perp_base import (
    PerpExecutionProviderName,
    PerpProviderStatus,
)


class ExecutionProviderSelectionRequest(BaseModel):
    provider: ExecutionProviderName


class ExecutionProviderSelectionResponse(BaseModel):
    active: ExecutionProviderName
    providers: list[ExecutionProviderStatus]
    selection_scope: str = Field(
        default="process",
        description="Selection resets to config on restart unless persisted in RuntimeState.",
    )


class PerpProviderSelectionRequest(BaseModel):
    provider: PerpExecutionProviderName


class PerpProviderSelectionResponse(BaseModel):
    active: PerpExecutionProviderName
    providers: list[PerpProviderStatus]
    selection_scope: str = Field(
        default="process",
        description="Selection resets to config on restart unless persisted in RuntimeState.",
    )


class ExecutionWalletProviderView(BaseModel):
    provider: str
    market: Literal["spot", "perp"]
    address: str | None
    network: str
    configured: bool
    active: bool
    balance_bnb: str | None
    balance_status: str


class ExecutionWalletAddressView(BaseModel):
    address: str
    active: bool
    network: str
    balance_bnb: str | None
    balance_status: str


class RpcEndpointView(BaseModel):
    index: int
    label: str
    active: bool
    reachable: bool
    latency_ms: int | None
    chain_id: int | None
    status: Literal["reachable", "unreachable", "chain_mismatch"]


class ExecutionWalletsResponse(BaseModel):
    network: str
    bsc_network: Literal["testnet", "mainnet"]
    chain_id: int
    active_wallet_address: str | None
    spot_active_provider: str
    perp_active_provider: str
    available_wallets: list[ExecutionWalletAddressView]
    active_rpc_endpoint_index: int | None
    wallets: list[ExecutionWalletProviderView]
    rpc_endpoints: list[RpcEndpointView]


class RpcEndpointSelectionRequest(BaseModel):
    index: int


class ExecutionNetworkSelectionRequest(BaseModel):
    network: Literal["testnet", "mainnet"]


class ExecutionWalletSelectionRequest(BaseModel):
    address: str
