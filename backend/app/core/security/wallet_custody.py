"""Encrypted EVM keystore custody boundary.

The provider reads encrypted key material only when explicitly constructed at
runtime. Callers must obtain the passphrase from an external secret source and
must never log either the passphrase or the keystore path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount


class WalletCustodyError(RuntimeError):
    """Raised when encrypted wallet material cannot be opened safely."""


class EncryptedKeystoreWallet:
    """Wallet provider backed by a standard encrypted Web3 keystore JSON."""

    def __init__(
        self,
        encrypted_keystore_path: str,
        passphrase: str,
        *,
        signing_policy: Any,
    ) -> None:
        if not encrypted_keystore_path or not passphrase:
            raise WalletCustodyError("Encrypted keystore path and passphrase are required")
        if signing_policy is None:
            raise WalletCustodyError("A fail-closed signing policy is required")
        self._policy = signing_policy
        try:
            payload = json.loads(Path(encrypted_keystore_path).read_text(encoding="utf-8"))
            private_key = Account.decrypt(payload, passphrase)
            self._account: LocalAccount = Account.from_key(private_key)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise WalletCustodyError("Unable to decrypt the configured wallet keystore") from exc

    @property
    def address(self) -> str:
        return self._account.address

    def sign_transaction(self, transaction: dict[str, Any]) -> dict[str, Any]:
        signed = self._account.sign_transaction(transaction)
        return {
            "rawTransaction": signed.raw_transaction,
            "hash": signed.hash,
            "r": signed.r,
            "s": signed.s,
            "v": signed.v,
        }

    def sign_message(self, message: str) -> dict[str, Any]:
        signed = self._account.sign_message(encode_defunct(text=message))
        return {
            "messageHash": signed.message_hash,
            "signature": signed.signature,
            "r": signed.r,
            "s": signed.s,
            "v": signed.v,
        }

    def sign_typed_data(
        self,
        domain: dict[str, Any],
        types: dict[str, list[dict[str, str]]],
        message: dict[str, Any],
    ) -> dict[str, Any]:
        from bnbagent.signing import check

        check(self._policy, domain, types, message)
        message_types = {name: fields for name, fields in types.items() if name != "EIP712Domain"}
        signed = self._account.sign_typed_data(
            domain_data=domain,
            message_types=message_types,
            message_data=message,
        )
        return {
            "messageHash": signed.message_hash,
            "signature": signed.signature,
            "r": signed.r,
            "s": signed.s,
            "v": signed.v,
        }
