"""Volume scambiato: somma di tutte le gambe, spot e perp.

Runnable locally: tocca solo il lato di lettura (repository + viste), mai
``agent.service``, quindi non tira dentro la catena web3/ckzg che non ha wheel
per Windows ARM64.

Le proprieta' che contano:
- il volume e' il TOTALE scambiato, aperture e chiusure comprese: non e' il
  capitale impegnato, e sul perp e' il NOZIONALE (size x prezzo);
- una riga non ``confirmed`` non entra nella somma, anche se oggi tutti i trade
  nascono confermati: il default del modello e' ``prepared``;
- "oggi" e' da mezzanotte UTC, la stessa convenzione delle altre viste.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.trades import (
    PerpTradeRepository,
    SpotTradeRepository,
)

USER_ID = str(UUID("00000000-0000-0000-0000-000000000001"))
ALTRO_UTENTE = str(UUID("00000000-0000-0000-0000-000000000002"))
OGGI = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
MEZZANOTTE = OGGI.replace(hour=0, minute=0, second=0, microsecond=0)
IERI = OGGI - timedelta(days=1)


@pytest.fixture()
async def db(tmp_path: Path):
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'volume.db'}")
    yield
    await close_db()


def _spot(
    seq: int,
    amount_quote: Decimal | None,
    *,
    quando: datetime = OGGI,
    status: str = "confirmed",
    user_id: str = USER_ID,
) -> SpotTrade:
    return SpotTrade(
        trade_id=f"s{seq}",
        user_id=user_id,
        asset="BTC",
        side="buy",
        amount=Decimal("1"),
        price=Decimal("100"),
        amount_quote=amount_quote,
        status=status,
        timestamp_utc=quando,
    )


def _perp(
    seq: int,
    size: Decimal,
    price: Decimal,
    *,
    direction: str = "open",
    quando: datetime = OGGI,
    status: str = "confirmed",
    user_id: str = USER_ID,
) -> PerpTrade:
    return PerpTrade(
        trade_id=f"p{seq}",
        user_id=user_id,
        asset="LINK",
        side="long",
        direction=direction,
        size=size,
        price=price,
        leverage=10,
        status=status,
        venue="dry_run",
        timestamp_utc=quando,
    )


async def _somma(righe: list, repo_cls):
    async with get_session_factory()() as session:
        for r in righe:
            session.add(r)
        await session.commit()
        return await repo_cls(session).sum_volume(USER_ID, since=MEZZANOTTE)


# ── nessun trade ───────────────────────────────────────────────────────────


async def test_utente_senza_trade_ha_volume_zero(db) -> None:
    """Zero, non None: la vista deve poter formattare il valore senza controlli."""
    totale, oggi = await _somma([], SpotTradeRepository)
    assert (totale, oggi) == (Decimal("0"), Decimal("0"))

    totale_p, oggi_p = await _somma([], PerpTradeRepository)
    assert (totale_p, oggi_p) == (Decimal("0"), Decimal("0"))


# ── somma corretta ─────────────────────────────────────────────────────────


async def test_spot_somma_amount_quote(db) -> None:
    totale, _ = await _somma(
        [_spot(1, Decimal("250.50")), _spot(2, Decimal("99.50"))],
        SpotTradeRepository,
    )
    assert totale == Decimal("350.00")


async def test_perp_somma_il_nozionale_non_la_size(db) -> None:
    """size x prezzo, non size: e' il punto dove un errore passerebbe inosservato.

    Con size e prezzo diversi fra loro e fra i due trade, sommare la size o
    moltiplicare per il prezzo sbagliato darebbe un numero comunque plausibile.
    """
    totale, _ = await _somma(
        [
            _perp(1, Decimal("2"), Decimal("150")),   # 300
            _perp(2, Decimal("0.5"), Decimal("400"), direction="close"),  # 200
        ],
        PerpTradeRepository,
    )
    assert totale == Decimal("500")


async def test_perp_conta_ogni_gamba(db) -> None:
    """Apertura e chiusura contano entrambe: il volume e' il totale scambiato."""
    totale, _ = await _somma(
        [
            _perp(1, Decimal("10"), Decimal("100"), direction="open"),
            _perp(2, Decimal("10"), Decimal("110"), direction="close"),
        ],
        PerpTradeRepository,
    )
    assert totale == Decimal("2100")  # 1000 + 1100, non 1000


# ── finestra "oggi" ────────────────────────────────────────────────────────


async def test_oggi_esclude_ieri_e_include_oggi(db) -> None:
    totale, oggi = await _somma(
        [
            _spot(1, Decimal("1000"), quando=IERI),
            _spot(2, Decimal("70"), quando=OGGI),
        ],
        SpotTradeRepository,
    )
    assert totale == Decimal("1070")
    assert oggi == Decimal("70")


async def test_oggi_su_perp_usa_il_nozionale(db) -> None:
    totale, oggi = await _somma(
        [
            _perp(1, Decimal("3"), Decimal("100"), quando=IERI),   # 300
            _perp(2, Decimal("2"), Decimal("50"), quando=OGGI),    # 100
        ],
        PerpTradeRepository,
    )
    assert totale == Decimal("400")
    assert oggi == Decimal("100")


# ── righe che NON devono entrare ───────────────────────────────────────────


async def test_status_non_confirmed_resta_fuori(db) -> None:
    """Il default del modello e' "prepared": una somma non deve raccoglierlo."""
    totale, oggi = await _somma(
        [
            _spot(1, Decimal("100")),
            _spot(2, Decimal("999"), status="prepared"),
        ],
        SpotTradeRepository,
    )
    assert totale == Decimal("100")
    assert oggi == Decimal("100")

    totale_p, _ = await _somma(
        [
            _perp(1, Decimal("1"), Decimal("100")),
            _perp(2, Decimal("50"), Decimal("100"), status="prepared"),
        ],
        PerpTradeRepository,
    )
    assert totale_p == Decimal("100")


async def test_un_importo_nullo_e_impossibile_per_vincolo(db) -> None:
    """Il mandato chiedeva un filtro IS NOT NULL sull'importo: non serve.

    `spot_trades.amount_quote` e' `nullable=False`, e lo sono anche `size` e
    `price` sul perp: una riga senza importo non puo' esistere, il database la
    rifiuta. Questo test documenta il vincolo su cui poggia l'assenza del
    filtro — se un domani la colonna diventasse nullable, fallirebbe qui e
    ricorderebbe di rimettere la guardia.
    """
    import sqlalchemy.exc

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await _somma([_spot(1, None)], SpotTradeRepository)


async def test_il_volume_di_un_altro_utente_non_entra(db) -> None:
    totale, _ = await _somma(
        [
            _spot(1, Decimal("40")),
            _spot(2, Decimal("5000"), user_id=ALTRO_UTENTE),
        ],
        SpotTradeRepository,
    )
    assert totale == Decimal("40")
