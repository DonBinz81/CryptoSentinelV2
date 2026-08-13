"""One-time script: transfer tBNB from old wallet to TWAK wallet."""
from web3 import Web3
from getpass import getpass

RPC = "https://bsc-testnet-rpc.publicnode.com"
TO = "0x5354d789d065d7a6CaA4287674261bE517AF6104"
CHAIN_ID = 97

w3 = Web3(Web3.HTTPProvider(RPC))
pk = getpass("Private key del vecchio wallet: ")
acct = w3.eth.account.from_key(pk)
balance = w3.eth.get_balance(acct.address)
print(f"From: {acct.address}")
print(f"Balance: {w3.from_wei(balance, 'ether')} tBNB")

gas_price = w3.eth.gas_price
gas_cost = 21000 * gas_price
send_amount = balance - gas_cost

if send_amount <= 0:
    print("Balance insufficiente per coprire il gas")
    exit(1)

print(f"Invio {w3.from_wei(send_amount, 'ether')} tBNB a {TO}")
confirm = input("Conferma (y/n): ")
if confirm.lower() != "y":
    print("Annullato")
    exit(0)

tx = {
    "to": TO,
    "value": send_amount,
    "gas": 21000,
    "gasPrice": gas_price,
    "nonce": w3.eth.get_transaction_count(acct.address),
    "chainId": CHAIN_ID,
}
signed = acct.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f"Inviato! TX: {tx_hash.hex()}")
print(f"Verifica: https://testnet.bscscan.com/tx/{tx_hash.hex()}")