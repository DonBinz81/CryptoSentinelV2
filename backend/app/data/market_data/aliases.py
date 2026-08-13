"""Stable application asset IDs and provider-specific slug aliases."""

from __future__ import annotations

# CryptoSentinel historically persisted CoinGecko IDs in favorites and alerts.
# Keep those IDs stable while translating only at provider boundaries.
CMC_SLUG_BY_APP_ID: dict[str, str] = {
    "avalanche-2": "avalanche",
    "binancecoin": "bnb",
    "hedera-hashgraph": "hedera",
    "injective-protocol": "injective",
    "leo-token": "unus-sed-leo",
    "matic-network": "polygon",
    "near": "near-protocol",
    "polkadot": "polkadot-new",
    "render-token": "render",
    "ripple": "xrp",
    "staked-ether": "steth",
    "the-open-network": "toncoin",
}

APP_ID_BY_CMC_SLUG: dict[str, str] = {
    cmc_slug: app_id for app_id, cmc_slug in CMC_SLUG_BY_APP_ID.items()
}


def cmc_slug_for_app_id(asset_id: str) -> str:
    """Translate a stable application ID to the CMC slug when it differs."""

    normalized = asset_id.lower()
    return CMC_SLUG_BY_APP_ID.get(normalized, normalized)


def app_id_for_cmc_slug(slug: str) -> str:
    """Translate a CMC slug back to the stable application ID."""

    normalized = slug.lower()
    return APP_ID_BY_CMC_SLUG.get(normalized, normalized)
