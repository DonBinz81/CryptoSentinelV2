"""Override manuale del guardiano: un layer sopra l'automatico, non al posto suo.

Il requisito che governa tutto: l'automatico continua a girare mentre l'override
è attivo, e premendo AUTO l'effettivo torna all'automatico CORRENTE — che nel
frattempo può essere cambiato. Se l'override sovrascrivesse lo stato non ci
sarebbe più nessun automatico a cui tornare.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.agent.guardian import GREEN, RED, YELLOW, GuardianConfig, RegimeGuardian

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
USER = "00000000-0000-0000-0000-0000000000aa"


@pytest.fixture()
def cfg() -> GuardianConfig:
    return GuardianConfig(enabled=True, window_hours=6, yellow_stops=1, red_stops=2, reentry_hours=6)


def _guardian(suffix: str) -> RegimeGuardian:
    """Un utente diverso per test: lo stato è persistito per user_id."""
    g = RegimeGuardian(f"{USER[:-2]}{suffix}")
    g._loaded = True  # niente lettura da RuntimeState: si parte puliti
    return g


# ── il livello effettivo ───────────────────────────────────────────────────


def test_without_override_effective_equals_automatic(cfg) -> None:
    g = _guardian("01")
    assert g.effective_state == g.state == GREEN


def test_override_changes_only_the_effective_level(cfg) -> None:
    """Il cuore del modello: l'automatico non viene toccato."""
    g = _guardian("02")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    g.record_stop(asset="INJ", pnl_usd=-8.0, now=NOW, cfg=cfg)
    assert g.state == RED

    g.set_manual_override(GREEN, NOW)
    assert g.effective_state == GREEN, "il motore deve obbedire all'override"
    assert g.state == RED, "l'automatico non deve essere toccato"


def test_auto_returns_to_the_current_automatic_level(cfg) -> None:
    """Esempio di David: automatico RED, forzo GREEN, premo AUTO -> torna RED."""
    g = _guardian("03")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    g.record_stop(asset="INJ", pnl_usd=-8.0, now=NOW, cfg=cfg)
    g.set_manual_override(GREEN, NOW)
    assert g.effective_state == GREEN

    g.clear_manual_override(NOW)
    assert g.effective_state == RED
    assert g.manual_override is None


def test_the_machine_keeps_running_under_the_override(cfg) -> None:
    """Mentre l'override è attivo l'automatico continua a salire di livello."""
    g = _guardian("04")
    g.set_manual_override(GREEN, NOW)
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    assert g.state == YELLOW, "l'automatico deve reagire allo stop"
    assert g.effective_state == GREEN, "l'effettivo resta quello forzato"

    g.record_stop(asset="INJ", pnl_usd=-8.0, now=NOW, cfg=cfg)
    assert g.state == RED
    assert g.effective_state == GREEN

    g.clear_manual_override(NOW)
    assert g.effective_state == RED, "tornando in AUTO si eredita cio' che e' successo nel frattempo"


# ── quello che l'override NON deve toccare ─────────────────────────────────


def test_override_does_not_move_the_countdown_anchor(cfg) -> None:
    """David: "senza resettare timer, contatori o informazioni che il sistema
    automatico stava già mantenendo". `changed_at` è l'ancora della
    de-escalation: se l'override la spostasse, il countdown ripartirebbe."""
    g = _guardian("05")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    prima = g._changed_at

    g.set_manual_override(GREEN, NOW + timedelta(hours=1))
    assert g._changed_at == prima

    g.clear_manual_override(NOW + timedelta(hours=2))
    assert g._changed_at == prima


def test_override_does_not_touch_the_stop_counters(cfg) -> None:
    g = _guardian("06")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    prima = g.stops_in_window(NOW, cfg)

    g.set_manual_override(RED, NOW)
    assert g.stops_in_window(NOW, cfg) == prima
    g.clear_manual_override(NOW)
    assert g.stops_in_window(NOW, cfg) == prima


def test_override_does_not_clear_the_brain_explanation(cfg) -> None:
    g = _guardian("07")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    g.record_explanation(text="mercato in strappo", at=NOW, for_change_at=g._changed_at)
    g.set_manual_override(GREEN, NOW)
    assert g._explanation == "mercato in strappo"


def test_de_escalation_still_runs_under_the_override(cfg) -> None:
    """La macchina automatica deve poter scendere di livello anche mentre
    l'override è attivo: e' proprio cio' che si eredita premendo AUTO."""
    g = _guardian("08")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    assert g.state == YELLOW
    g.set_manual_override(RED, NOW)

    dopo = NOW + timedelta(hours=cfg.reentry_hours + 1)
    g.evaluate(now=dopo, cfg=cfg)
    assert g.state == GREEN, "l'automatico e' rientrato da solo"
    assert g.effective_state == RED, "l'effettivo resta quello forzato"


# ── persistenza ────────────────────────────────────────────────────────────
#
# Questi due usano un database vero: gli altri girano in memoria (_loaded=True,
# come i test del guardiano esistenti) e non scriverebbero su RuntimeState,
# quindi non potrebbero dimostrare nulla sul riavvio.


@pytest.fixture()
def db(tmp_path):
    from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db

    reset_sync_db()
    init_sync_db(f"sqlite:///{tmp_path / 'guardian.db'}")
    create_all_sync()
    yield
    reset_sync_db()


def test_override_survives_a_restart(db, cfg) -> None:
    """Il blob e' gia' persistito: due chiavi in piu', nessuna migrazione."""
    g = RegimeGuardian(f"{USER[:-2]}09")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    g.set_manual_override(GREEN, NOW)

    ripartito = RegimeGuardian(g.user_id)  # rilegge da RuntimeState
    assert ripartito.manual_override == GREEN
    assert ripartito.effective_state == GREEN
    assert ripartito.state == YELLOW, "anche l'automatico deve sopravvivere"


def test_clearing_the_override_survives_a_restart(db, cfg) -> None:
    g = RegimeGuardian(f"{USER[:-2]}10")
    g.set_manual_override(RED, NOW)
    g.clear_manual_override(NOW)

    ripartito = RegimeGuardian(g.user_id)
    assert ripartito.manual_override is None
    assert ripartito.effective_state == GREEN


# ── snapshot per l'app ─────────────────────────────────────────────────────


def test_snapshot_exposes_the_three_levels(cfg) -> None:
    g = _guardian("11")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    g.record_stop(asset="INJ", pnl_usd=-8.0, now=NOW, cfg=cfg)
    g.set_manual_override(GREEN, NOW)

    snap = g.snapshot(NOW, cfg)
    assert snap["automatic_level"] == RED
    assert snap["effective_level"] == GREEN
    assert snap["manual_override"]["level"] == GREEN
    assert snap["manual_override"]["at"] is not None
    # `state` resta "cio' che il motore fa", cosi' il banner esistente e la V1
    # non cambiano comportamento: senza override i due coincidono.
    assert snap["state"] == GREEN


def test_snapshot_without_override_keeps_the_old_shape(cfg) -> None:
    g = _guardian("12")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    snap = g.snapshot(NOW, cfg)
    assert snap["manual_override"] is None
    assert snap["state"] == snap["automatic_level"] == snap["effective_level"] == YELLOW


def test_countdown_fields_still_refer_to_the_automatic_machine(cfg) -> None:
    g = _guardian("13")
    g.record_stop(asset="LINK", pnl_usd=-10.0, now=NOW, cfg=cfg)
    prima = g.snapshot(NOW, cfg)
    g.set_manual_override(GREEN, NOW + timedelta(hours=1))
    dopo = g.snapshot(NOW + timedelta(hours=1), cfg)
    assert dopo["last_stop_at"] == prima["last_stop_at"]
    assert dopo["changed_at"] == prima["changed_at"]
    assert dopo["reentry_hours"] == prima["reentry_hours"]


# ── validazione ────────────────────────────────────────────────────────────


def test_an_unknown_level_is_refused(cfg) -> None:
    g = _guardian("14")
    with pytest.raises(ValueError):
        g.set_manual_override("blue", NOW)
    assert g.manual_override is None


def test_clearing_when_nothing_is_set_is_harmless(cfg) -> None:
    g = _guardian("15")
    result = g.clear_manual_override(NOW)
    assert result["previous"] is None
    assert g.effective_state == GREEN
