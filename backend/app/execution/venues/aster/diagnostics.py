"""Aster connection diagnostics — the single source used by App, Dashboard and CLI.

STRICTLY READ-ONLY. Every call made here is a GET on an informational endpoint:
this code cannot place, modify or cancel an order, and cannot move funds.

Each check reports its own outcome so a failure says *which* step broke, instead
of a generic "connection failed".
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.execution.venues.aster.client import AsterClient, AsterError, short_address

logger = get_logger("execution.venue.aster.diagnostics")

OK = "ok"
WARNING = "warning"
ERROR = "error"
CRITICAL = "critical"


@dataclass
class Check:
    """One diagnostic step, in user-facing language."""

    key: str
    label: str
    status: str
    detail: str
    technical: str | None = None  # original API code, shown in the expandable section


@dataclass
class DiagnosticsReport:
    overall: str
    summary: str
    checks: list[Check] = field(default_factory=list)
    started_at: str = ""
    duration_ms: int = 0
    account: str | None = None      # abbreviated address, never the full key material
    subaccount_name: str | None = None
    blocked: bool = False           # true on CRITICAL: Aster operations must stay disabled

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [asdict(c) for c in self.checks]
        return data


def _describe(exc: AsterError) -> tuple[str, str]:
    """Translate an Aster failure into something a person can act on."""
    code = (exc.code or "").upper()
    status = exc.status
    if code == "TIMEOUT":
        return ("Aster non ha risposto entro il tempo previsto. "
                "Riprova; se persiste, verifica la connessione della VPS.", code)
    if code == "NETWORK":
        return ("Impossibile raggiungere Aster. Verifica connettività di rete e "
                "che l'indirizzo del servizio sia corretto.", code)
    if status in (401, 403):
        return ("Aster ha rifiutato l'autenticazione. Verifica indirizzo del wallet API, "
                "chiave di firma e che la chiave non sia scaduta.", code or str(status))
    if status == 429:
        return ("Troppe richieste in poco tempo (rate limit di Aster). "
                "Attendi qualche secondo e riprova.", code or "429")
    if status and 500 <= status < 600:
        return ("Aster ha restituito un errore interno. Il problema è dalla loro parte: "
                "riprova più tardi.", code or str(status))
    return (f"Aster ha rifiutato la richiesta: {exc}", code or (str(status) if status else "-"))


async def run_connection_test(settings) -> DiagnosticsReport:
    """Run the full read-only diagnostic sequence."""
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    checks: list[Check] = []
    logger.info("aster_test_started")

    base_url = getattr(settings, "aster_base_url", "")
    account_address = getattr(settings, "aster_account_address", "")
    api_wallet = getattr(settings, "aster_api_wallet_address", "")
    private_key = getattr(settings, "aster_api_wallet_private_key", "")
    subaccount = getattr(settings, "aster_subaccount_name", "")

    def finish(overall: str, summary: str, *, blocked: bool = False) -> DiagnosticsReport:
        duration = int((time.perf_counter() - started) * 1000)
        logger.info("aster_test_completed", overall=overall, duration_ms=duration)
        return DiagnosticsReport(
            overall=overall,
            summary=summary,
            checks=checks,
            started_at=started_at.isoformat(),
            duration_ms=duration,
            account=short_address(account_address),
            subaccount_name=subaccount or None,
            blocked=blocked,
        )

    # 1. Configuration ─────────────────────────────────────────────────────
    missing = [
        name
        for name, value in (
            ("indirizzo account", account_address),
            ("indirizzo wallet API", api_wallet),
            ("chiave di firma", private_key),
        )
        if not value
    ]
    if missing:
        checks.append(Check(
            "config", "Configurazione", ERROR,
            "Mancano queste voci nella configurazione: " + ", ".join(missing)
            + ". Vanno inserite nel file .env sulla VPS.",
        ))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")
    checks.append(Check(
        "config", "Configurazione", OK,
        f"Configurazione presente. Account {short_address(account_address)}, "
        f"wallet API {short_address(api_wallet)}.",
    ))

    client = AsterClient(
        base_url=base_url,
        account_address=account_address,
        api_wallet_address=api_wallet,
        api_wallet_private_key=private_key,
    )

    # 2. Key/address coherence — catches a mismatched pair before signing ──
    if not client.signer_matches_key():
        checks.append(Check(
            "signer", "Coerenza credenziali", ERROR,
            "La chiave di firma non corrisponde all'indirizzo del wallet API configurato. "
            "Probabilmente appartengono a due wallet diversi.",
        ))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")
    checks.append(Check(
        "signer", "Coerenza credenziali", OK,
        "La chiave di firma corrisponde all'indirizzo del wallet API.",
    ))

    # 3. Reachability (public, unsigned) ───────────────────────────────────
    try:
        info = await client.public_exchange_info()
        markets = len(info.get("symbols", [])) if isinstance(info, dict) else 0
        checks.append(Check(
            "reachability", "Connessione API", OK,
            f"Servizio Aster raggiungibile: {markets} mercati pubblicati.",
        ))
    except AsterError as exc:
        detail, code = _describe(exc)
        checks.append(Check("reachability", "Connessione API", ERROR, detail, code))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")

    # 4. Authentication + account identity ─────────────────────────────────
    account_data: Any = None
    try:
        account_data = await client.account()
        checks.append(Check(
            "auth", "Autenticazione", OK,
            "Aster ha accettato la firma: le credenziali sono valide.",
        ))
    except AsterError as exc:
        detail, code = _describe(exc)
        checks.append(Check("auth", "Autenticazione", ERROR, detail, code))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")

    # Identity: if Aster returns an address, it must be the configured one.
    returned = None
    if isinstance(account_data, dict):
        for key in ("user", "account", "address", "tradeAddress"):
            value = account_data.get(key)
            if isinstance(value, str) and value.startswith("0x"):
                returned = value
                break
    if returned and returned.lower() != account_address.lower():
        checks.append(Check(
            "identity", "Identità account", CRITICAL,
            "L'account restituito da Aster non corrisponde a quello configurato "
            f"({short_address(returned)} invece di {short_address(account_address)}). "
            "Le operazioni su Aster restano bloccate finché non viene risolto.",
        ))
        return finish(CRITICAL, "CONNESSIONE ASTER: ERRORE CRITICO", blocked=True)
    checks.append(Check(
        "identity", "Identità account", OK if returned else WARNING,
        f"Account confermato: {short_address(returned)}." if returned
        else "Aster non restituisce un indirizzo verificabile in questa risposta: "
             "impossibile confrontarlo con quello configurato.",
    ))

    # 5. Read permission ───────────────────────────────────────────────────
    checks.append(Check(
        "read", "Permessi di lettura", OK,
        "I dati dell'account sono leggibili: il permesso READ è attivo.",
    ))

    # 6. Balance ───────────────────────────────────────────────────────────
    try:
        balances = await client.balance()
        funded = [
            b for b in (balances if isinstance(balances, list) else [])
            if _as_float(b.get("balance")) > 0
        ]
        detail = f"Saldo leggibile: {len(funded)} asset con disponibilità." if funded else \
            "Saldo leggibile, al momento nessun asset con disponibilità."
        checks.append(Check("balance", "Saldo", OK if funded else WARNING, detail))
    except AsterError as exc:
        detail, code = _describe(exc)
        checks.append(Check("balance", "Saldo", ERROR, detail, code))

    # 7. Positions ─────────────────────────────────────────────────────────
    try:
        positions = await client.position_risk()
        open_positions = [
            p for p in (positions if isinstance(positions, list) else [])
            if _as_float(p.get("positionAmt")) != 0
        ]
        checks.append(Check(
            "positions", "Posizioni", OK,
            f"Posizioni leggibili: {len(open_positions)} aperte su Aster.",
        ))
    except AsterError as exc:
        detail, code = _describe(exc)
        checks.append(Check("positions", "Posizioni", ERROR, detail, code))

    # 8. Perp access + real commission rate ────────────────────────────────
    try:
        rate = await client.commission_rate("BTCUSDT")
        maker = rate.get("makerCommissionRate") if isinstance(rate, dict) else None
        taker = rate.get("takerCommissionRate") if isinstance(rate, dict) else None
        checks.append(Check(
            "perp", "Accesso Perpetual", OK,
            f"Perpetual accessibile. Commissioni dell'account: maker {maker}, taker {taker}."
            if maker is not None else "Perpetual accessibile.",
        ))
    except AsterError as exc:
        detail, code = _describe(exc)
        checks.append(Check("perp", "Accesso Perpetual", ERROR, detail, code))

    statuses = {c.status for c in checks}
    if CRITICAL in statuses:
        return finish(CRITICAL, "CONNESSIONE ASTER: ERRORE CRITICO", blocked=True)
    if ERROR in statuses:
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")
    if WARNING in statuses:
        return finish(WARNING, "CONNESSIONE ASTER: OPERATIVA CON AVVISI")
    return finish(OK, "CONNESSIONE ASTER: OPERATIVA")


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
