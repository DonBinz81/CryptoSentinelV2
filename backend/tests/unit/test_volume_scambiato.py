"""Volume scambiato: somma di tutte le gambe, spot e perp.

Runnable locally: tocca solo il lato di lettura (repository + viste), mai
``agent.service``, quindi non tira dentro la catena web3/ckzg che non ha wheel
per Windows ARM64.

Le proprieta' che contano:
- il volume e' il TOTALE scambiato, aperture e chiusure comprese: non e' il
  capitale impegnato, e sul perp e' il NOZIONALE (size x prezzo);
- 🔴 le aperture ``prepared`` ENTRANO nella somma: nascono cosi' e nessuno le
  promuove mai, quindi filtrare sullo status dimezzava il volume;
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


async def test_le_aperture_prepared_ENTRANO_nella_somma(db) -> None:
    """🔴 Il test che prima diceva l'opposto, e congelava un difetto.

    Le gambe di APERTURA nascono `prepared` (`agent/service.py`, entrambi i
    mercati) e nessuno le promuove mai: solo chiusure, rebuy e scale-in nascono
    `confirmed`. Filtrare sullo status quindi non escludeva "ordini non
    eseguiti" — dimezzava il volume, scartando ogni apertura.

    Che siano eseguite e' dimostrato dal codice (la riga viene scritta solo dopo
    `entry_execution.confirmed`) e dai dati di produzione: 252 aperture
    `prepared`, 252 posizioni perp corrispondenti.
    """
    totale, oggi = await _somma(
        [
            _spot(1, Decimal("100")),                        # chiusura
            _spot(2, Decimal("60"), status="prepared"),      # apertura
        ],
        SpotTradeRepository,
    )
    assert totale == Decimal("160"), "l'apertura prepared deve contare"
    assert oggi == Decimal("160")

    totale_p, _ = await _somma(
        [
            _perp(1, Decimal("1"), Decimal("100")),                       # 100
            _perp(2, Decimal("2"), Decimal("100"), status="prepared"),    # 200
        ],
        PerpTradeRepository,
    )
    assert totale_p == Decimal("300"), "il nozionale dell'apertura deve contare"


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


# ── collegamento repository -> viste ───────────────────────────────────────
#
# I test sopra coprono sum_volume. Questi coprono il CABLAGGIO, che era scoperto:
# invertire i due campi in views.py, o dimenticarli nel ramo anticipato di
# global_view, non faceva fallire nulla e produceva numeri plausibili.


async def _viste(righe: list):
    from backend.app.persistence.views import ViewService

    async with get_session_factory()() as session:
        for r in righe:
            session.add(r)
        await session.commit()
        vs = ViewService(session)
        return (
            await vs.spot_view(USER_ID),
            await vs.perp_view(USER_ID),
            await vs.global_view(USER_ID),
        )


async def test_le_viste_non_scambiano_totale_e_oggi(db) -> None:
    """Totale e quota odierna devono finire ognuno nel proprio campo.

    Numeri scelti perche' uno scambio sia visibile: se invertiti, Vol Tot
    mostrerebbe 70 e Vol Day 1070 — entrambi plausibili.
    """
    spot, perp, glob = await _viste(
        [
            _spot(1, Decimal("1000"), quando=IERI),
            _spot(2, Decimal("70"), quando=OGGI),
            _perp(1, Decimal("3"), Decimal("100"), quando=IERI),  # 300
            _perp(2, Decimal("2"), Decimal("50"), quando=OGGI),   # 100
        ]
    )
    assert (spot.volume_total_usd, spot.volume_today_usd) == (Decimal("1070"), Decimal("70"))
    assert (perp.volume_total_usd, perp.volume_today_usd) == (Decimal("400"), Decimal("100"))
    # Global = spot + perp, non uno dei due
    assert glob.volume_total_usd == Decimal("1470")
    assert glob.volume_today_usd == Decimal("170")


async def test_global_view_senza_portfolio_riporta_comunque_il_volume(db) -> None:
    """global_view ha DUE punti di uscita: quello anticipato non deve dare zero.

    Nessuna riga in `portfolio`, quindi si passa dal return anticipato. Senza
    questo test, dimenticare li' i due campi avrebbe mostrato Vol Tot $0,00 con
    l'agente che aveva scambiato regolarmente.
    """
    _, _, glob = await _viste([_perp(1, Decimal("4"), Decimal("25"))])  # 100
    assert glob.volume_total_usd == Decimal("100")
    assert glob.volume_today_usd == Decimal("100")
