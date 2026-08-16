"""Profit Lock Ratchet — schema + funzioni pure.

Il ratchet lavora SOLO nel tratto TP1→TP2 e fa tre cose:
  1. uscite parziali agli scalini, con quote CUMULATIVE sul residuo post-TP1;
  2. "breakeven del ratchet": stop fisso a una quota del tratto, armato dallo
     scalino configurato in poi;
  3. oltre il TP2 lascia correre con un trailing percentuale.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.agent.service import (
    _ratchet_breakeven_price,
    _ratchet_level,
    _ratchet_progress,
)
from backend.app.schemas.mobile_agent import AgentMobileSettings

# (punto del tratto TP1→TP2, quota cumulativa del residuo da chiudere)
STEPS = [(0.50, 0.25), (0.70, 0.50), (0.95, 0.80)]


def D(x):
    return Decimal(str(x))


# --------------------------- schema: migrazione modalità ---------------------------

def test_protection_mode_derived_from_trailing_on():
    s = AgentMobileSettings(perp_trailing_enabled=True)
    assert s.perp_protection_mode == "trailing"
    assert s.perp_trailing_enabled is True


def test_protection_mode_derived_from_trailing_off():
    s = AgentMobileSettings(perp_trailing_enabled=False)
    assert s.perp_protection_mode == "off"


def test_profit_lock_mode_forces_trailing_off():
    """Scegliendo profit_lock il trailing ATR viene spento (un solo gestore dello stop)."""
    s = AgentMobileSettings(perp_protection_mode="profit_lock")
    assert s.perp_trailing_enabled is False


def test_invalid_protection_mode_rejected():
    with pytest.raises(ValueError):
        AgentMobileSettings(perp_protection_mode="banana")


# --------------------------- schema: scalini e parametri ---------------------------

def test_default_steps_are_davids():
    s = AgentMobileSettings()
    assert list(s.perp_profit_lock_steps) == [(0.50, 0.25), (0.70, 0.50), (0.95, 0.80)]
    assert s.perp_ratchet_breakeven_pct == 50.0
    assert s.perp_ratchet_breakeven_after_step == 3
    assert s.perp_ratchet_run_beyond_tp2 is True
    assert s.perp_ratchet_trailing_pct == 1.0


def test_quota_may_exceed_level():
    """La quota da chiudere NON è vincolata a stare sotto il livello: sono grandezze diverse.

    Col vecchio significato ("profitto bloccato") il vincolo lock < soglia aveva senso;
    con "quanto chiudo" no — al 50% del tratto si può voler chiudere il 60%.
    """
    s = AgentMobileSettings(perp_profit_lock_steps=[(0.50, 0.60), (0.80, 0.90)])
    assert list(s.perp_profit_lock_steps) == [(0.50, 0.60), (0.80, 0.90)]


def test_last_step_may_close_everything():
    s = AgentMobileSettings(perp_profit_lock_steps=[(0.50, 0.50), (0.90, 1.0)])
    assert list(s.perp_profit_lock_steps)[-1][1] == 1.0


@pytest.mark.parametrize("bad", [
    [(0.8, 0.25), (0.6, 0.5)],        # livelli non crescenti
    [(0.6, 0.5), (0.8, 0.4)],         # quote non crescenti
    [(0.0, 0.25)],                    # livello fuori (0,1)
    [(0.6, 1.5)],                     # quota oltre 1
    [(0.6, 0.0)],                     # quota nulla
    [(0.6,)],                         # coppia malformata
])
def test_bad_steps_rejected(bad):
    with pytest.raises(ValueError):
        AgentMobileSettings(perp_profit_lock_steps=bad)


def test_breakeven_step_clamped_to_available_steps():
    """Riducendo gli scalini il breakeven si aggancia all'ultimo, senza far fallire il salvataggio."""
    s = AgentMobileSettings(
        perp_profit_lock_steps=[(0.50, 0.25), (0.90, 0.80)],
        perp_ratchet_breakeven_after_step=3,
    )
    assert s.perp_ratchet_breakeven_after_step == 2


# --------------------------- progresso sul tratto TP1→TP2 --------------------------

def test_progress_measured_from_tp1_not_entry():
    """Appena toccato il TP1 il progresso è 0, non 62,5% come sarebbe misurando dall'entry."""
    tp1, tp2 = D("102.5"), D(104)   # 2,5 e 4,0 ATR con ATR = 1
    assert _ratchet_progress(tp1, tp2, tp1, True) == D(0)
    assert _ratchet_progress(tp1, tp2, D("103.25"), True) == D("0.5")
    assert _ratchet_progress(tp1, tp2, D(104), True) == D(1)


def test_progress_clamped_and_guards():
    tp1, tp2 = D(100), D(110)
    assert _ratchet_progress(tp1, tp2, D(120), True) == D(1)      # oltre TP2 → 1
    assert _ratchet_progress(tp1, tp2, D(95), True) == D(0)       # sotto TP1 → 0
    assert _ratchet_progress(tp1, tp1, D(105), True) is None      # tratto nullo
    assert _ratchet_progress(None, tp2, D(105), True) is None     # senza TP1


def test_progress_short_symmetric():
    tp1, tp2 = D(100), D(90)
    assert _ratchet_progress(tp1, tp2, D(95), False) == D("0.5")


# --------------------------- livello raggiunto e quota cumulativa -------------------

def test_no_level_before_first_threshold():
    assert _ratchet_level(D("0.49"), STEPS) == (-1, D(0))


def test_levels_and_cumulative_quotas():
    assert _ratchet_level(D("0.50"), STEPS) == (0, D("0.25"))
    assert _ratchet_level(D("0.69"), STEPS) == (0, D("0.25"))
    assert _ratchet_level(D("0.70"), STEPS) == (1, D("0.50"))
    assert _ratchet_level(D("0.94"), STEPS) == (1, D("0.50"))
    assert _ratchet_level(D("0.95"), STEPS) == (2, D("0.80"))
    assert _ratchet_level(D(1), STEPS) == (2, D("0.80"))


def test_quotas_are_cumulative_not_chained():
    """Con residuo 30: 25% → 7,5; poi 50% totale → altri 7,5; poi 80% totale → altri 9.

    A catena sarebbero 7,5 / 11,25 / 9 e resterebbe molto meno.
    """
    base = D(30)
    closed = D(0)
    chiusure = []
    for prog in ["0.50", "0.70", "0.95"]:
        _, cum = _ratchet_level(D(prog), STEPS)
        chiusure.append(base * (cum - closed))
        closed = cum
    assert chiusure == [D("7.5"), D("7.5"), D("9.0")]
    assert base - sum(chiusure) == D(6)   # il 20% corre verso il TP2


# --------------------------- breakeven del ratchet ---------------------------------

def test_breakeven_price_is_a_fixed_point_of_the_span():
    tp1, tp2 = D("102.5"), D(104)
    assert _ratchet_breakeven_price(tp1, tp2, D("0.5"), True) == D("103.25")
    # short: simmetrico
    assert _ratchet_breakeven_price(D(100), D(90), D("0.5"), False) == D(95)


def test_breakeven_is_above_tp1_long_and_below_tp1_short():
    """Il breakeven del ratchet protegge SOPRA il parziale già incassato."""
    assert _ratchet_breakeven_price(D("102.5"), D(104), D("0.5"), True) > D("102.5")
    assert _ratchet_breakeven_price(D(100), D(90), D("0.5"), False) < D(100)
