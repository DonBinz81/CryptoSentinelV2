"""Create an encrypted Web3 keystore from interactive secret input."""

from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

from eth_account import Account

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "secrets" / "wallet-keystore.json"


class WalletEncryptionError(RuntimeError):
    """Raised when the encrypted keystore cannot be created safely."""


def _read_private_key() -> bytearray:
    value = getpass.getpass("Private key: ").strip()
    if value.lower().startswith("0x"):
        value = value[2:]
    try:
        key = bytearray.fromhex(value)
    except ValueError as exc:
        raise WalletEncryptionError("Invalid private key format") from exc
    finally:
        value = ""
    if len(key) != 32:
        for index in range(len(key)):
            key[index] = 0
        raise WalletEncryptionError("Private key must contain exactly 32 bytes")
    return key


def _read_passphrase() -> str:
    passphrase = getpass.getpass("Keystore passphrase: ")
    confirmation = getpass.getpass("Confirm passphrase: ")
    if not passphrase:
        raise WalletEncryptionError("Passphrase cannot be empty")
    if passphrase != confirmation:
        raise WalletEncryptionError("Passphrases do not match")
    return passphrase


def create_encrypted_keystore(
    private_key: bytearray,
    passphrase: str,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> str:
    """Encrypt a private key and write a new keystore without overwriting."""

    if output_path.exists():
        raise WalletEncryptionError("Encrypted wallet keystore already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        account = Account.from_key(bytes(private_key))
        payload: dict[str, Any] = Account.encrypt(account.key, passphrase)
        serialized = json.dumps(payload, separators=(",", ":"))
        with output_path.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.write("\n")
        try:
            os.chmod(output_path, 0o600)
        except OSError:
            pass
        return account.address
    except (OSError, TypeError, ValueError) as exc:
        raise WalletEncryptionError("Unable to create encrypted wallet keystore") from exc
    finally:
        for index in range(len(private_key)):
            private_key[index] = 0


def main() -> int:
    if len(sys.argv) != 1:
        print("This script accepts secrets only through interactive input.", file=sys.stderr)
        return 2
    private_key: bytearray | None = None
    try:
        private_key = _read_private_key()
        passphrase = _read_passphrase()
        address = create_encrypted_keystore(private_key, passphrase)
    except (WalletEncryptionError, EOFError, KeyboardInterrupt) as exc:
        if private_key is not None:
            for index in range(len(private_key)):
                private_key[index] = 0
        print(f"Keystore creation failed: {exc}", file=sys.stderr)
        return 1
    print("Encrypted wallet keystore created.")
    print(f"Wallet address: {address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
