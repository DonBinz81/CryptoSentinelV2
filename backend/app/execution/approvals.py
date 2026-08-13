"""Fail-closed ERC-20 approval policy."""

from web3 import Web3


class ApprovalPolicyError(ValueError):
    """Raised for unsafe approval requests."""


class ExactApprovalPolicy:
    def __init__(self, allowed_spenders: list[str]) -> None:
        self._allowed = {Web3.to_checksum_address(address) for address in allowed_spenders}

    def validate(self, spender: str, amount: int, required_amount: int) -> str:
        checked = Web3.to_checksum_address(spender)
        if checked not in self._allowed:
            raise ApprovalPolicyError("Spender is not in the DEX contract whitelist")
        if amount <= 0 or required_amount <= 0:
            raise ApprovalPolicyError("Approval amounts must be positive")
        if amount != required_amount:
            raise ApprovalPolicyError("Only exact, immediate-need approvals are allowed")
        return checked

