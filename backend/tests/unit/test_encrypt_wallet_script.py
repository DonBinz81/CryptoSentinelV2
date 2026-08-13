import json

from eth_account import Account

from backend.scripts.encrypt_wallet import create_encrypted_keystore


def test_create_encrypted_keystore_writes_only_encrypted_material(tmp_path) -> None:
    generated = Account.create()
    private_key = bytearray(generated.key)
    output_path = tmp_path / "wallet-keystore.json"

    address = create_encrypted_keystore(private_key, "test-passphrase", output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert address == generated.address
    assert payload["address"].lower() == generated.address.lower().removeprefix("0x")
    assert "crypto" in {key.lower() for key in payload}
    assert bytes(private_key) == bytes(32)
