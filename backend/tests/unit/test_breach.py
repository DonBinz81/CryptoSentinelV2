"""Unit tests for the breach persistence+bypass episode tracker (NOTE/64).

Pure-function tests: feed a sequence of (price, timestamp) samples through
evaluate_breach and check the events it emits. Thresholds mirror the
18-19/08 retrospective defaults (SL: 5s/0.15%, Smart SL: 900s/0.30%).
"""

from __future__ import annotations

import json

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backend.app.agent.breach import BreachRuleConfig, evaluate_breach

T0 = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
SL_CFG = BreachRuleConfig(persistence_seconds=5.0, bypass_pct=0.15)


def _step(state, level_price, price, is_long, t, cfg=SL_CFG):
    return evaluate_breach(
        state=state, level="SL", level_price=level_price, current_price=price,
        is_long=is_long, now=t, cfg=cfg,
    )


class TestEpisodeLifecycle:
    def test_price_on_safe_side_produces_no_episode(self):
        state, events = _step(None, 100.0, 101.0, is_long=True, t=T0)
        assert state is None and events == []

    def test_first_sample_beyond_starts_an_episode(self):
        # 0.1% depth: below bypass (0.15%), so only "started" fires here.
        state, events = _step(None, 100.0, 99.9, is_long=True, t=T0)
        assert state is not None
        assert [e.kind for e in events] == ["started"]

    def test_return_inside_level_ends_the_episode(self):
        state, _ = _step(None, 100.0, 99.0, is_long=True, t=T0)
        state, events = _step(state, 100.0, 100.5, is_long=True, t=T0 + timedelta(seconds=2))
        assert state is None
        assert [e.kind for e in events] == ["ended"]
        assert events[0].duration_s == 2.0

    def test_max_depth_tracks_the_worst_sample_in_the_episode(self):
        state, _ = _step(None, 100.0, 99.9, is_long=True, t=T0)  # 0.1%
        state, _ = _step(state, 100.0, 99.5, is_long=True, t=T0 + timedelta(seconds=1))  # 0.5%
        state, _ = _step(state, 100.0, 99.8, is_long=True, t=T0 + timedelta(seconds=2))  # 0.2%, not worse
        assert state["max_depth_pct"] == 0.5


class TestFiring:
    def test_short_flicker_never_fires(self):
        # NEAR 18/08: <1s, ~0.025% depth — must stay silent under 5s/0.15%.
        state, events = _step(None, 100.0, 99.975, is_long=True, t=T0)
        state, events = _step(state, 100.0, 100.1, is_long=True, t=T0 + timedelta(milliseconds=800))
        assert not any(e.kind == "rule_fired" for e in events)

    def test_persistence_fires_once_at_five_seconds(self):
        state, _ = _step(None, 100.0, 99.9, is_long=True, t=T0)
        for sec in (1, 2, 3, 4):
            state, events = _step(state, 100.0, 99.9, is_long=True, t=T0 + timedelta(seconds=sec))
            assert not any(e.kind == "rule_fired" for e in events), f"fired early at {sec}s"
        state, events = _step(state, 100.0, 99.9, is_long=True, t=T0 + timedelta(seconds=5))
        fired = [e for e in events if e.kind == "rule_fired"]
        assert len(fired) == 1 and fired[0].fired_by == "persistence"

    def test_fires_only_once_per_episode(self):
        """The latch must survive the REAL persistence path (NOTE/73).

        The first version of this test passed the same in-memory dict between
        steps and stayed green while production re-fired 24 times: service.py
        round-trips the state through JSON (DB column) on every tick, so the
        test must too, or it verifies a world that does not exist.
        """
        state, _ = _step(None, 100.0, 99.9, is_long=True, t=T0)
        state = json.loads(json.dumps(state))
        state, events = _step(state, 100.0, 99.9, is_long=True, t=T0 + timedelta(seconds=6))
        assert any(e.kind == "rule_fired" for e in events)
        state = json.loads(json.dumps(state))
        state, events2 = _step(state, 100.0, 99.9, is_long=True, t=T0 + timedelta(seconds=10))
        assert not any(e.kind == "rule_fired" for e in events2)

    def test_bch_regression_one_fired_across_many_roundtripped_samples(self):
        """Production replay (NOTE/73): BCH logged 24 rule_fired for ONE episode.

        Deep first sample fires the bypass; twenty more beyond-samples, each
        with the JSON round-trip service.py really does, must not re-fire.
        """
        state, events = _step(None, 100.0, 99.5, is_long=True, t=T0)
        fired = sum(1 for e in events if e.kind == "rule_fired")
        for k in range(1, 21):
            state = json.loads(json.dumps(state))
            state, events = _step(state, 100.0, 99.5, is_long=True, t=T0 + timedelta(seconds=5.6 * k))
            fired += sum(1 for e in events if e.kind == "rule_fired")
        assert fired == 1

    def test_input_state_is_never_mutated(self):
        """Purity is load-bearing: the caller detects change by comparing old
        vs new state, so mutating the input hides every change (NOTE/73)."""
        state, _ = _step(None, 100.0, 99.99, is_long=True, t=T0)
        frozen = json.dumps(state, sort_keys=True)
        _step(state, 100.0, 99.5, is_long=True, t=T0 + timedelta(seconds=6))
        assert json.dumps(state, sort_keys=True) == frozen

    def test_bypass_fires_immediately_on_deep_breach(self):
        # A crash-like tick: 0.5% depth on the very first sample, well before 5s.
        state, events = _step(None, 100.0, 99.5, is_long=True, t=T0)
        fired = [e for e in events if e.kind == "rule_fired"]
        assert len(fired) == 1 and fired[0].fired_by == "bypass"

    def test_short_side_is_symmetric(self):
        state, _ = _step(None, 100.0, 100.1, is_long=False, t=T0)
        for sec in (1, 2, 3, 4):
            state, events = _step(state, 100.0, 100.1, is_long=False, t=T0 + timedelta(seconds=sec))
            assert not any(e.kind == "rule_fired" for e in events)
        state, events = _step(state, 100.0, 100.1, is_long=False, t=T0 + timedelta(seconds=5))
        assert any(e.kind == "rule_fired" and e.fired_by == "persistence" for e in events)


class TestServicePersistencePath:
    """The NOTE/73 bug lived in the service integration, not in breach.py
    alone: the fired latch was set on a later sample via in-place mutation,
    service.py's identity check saw "no change", and pos.breach_state kept
    saying fired=false forever. This test walks the REAL path: the ORM field.
    """

    def test_latch_reaches_breach_state_when_fired_on_a_later_sample(self):
        from datetime import timedelta as _td

        from backend.app.agent.service import AgentService
        from backend.app.persistence.models.positions import PerpPosition
        from backend.app.schemas.mobile_agent import AgentMobileSettings

        service = AgentService.__new__(AgentService)  # no ctor: method under test uses no service state
        ms = AgentMobileSettings(perp_breach_mode="shadow")
        pos = PerpPosition(
            position_id="pos_test_note73", user_id="u", asset="BCH", side="long",
            entry_price=Decimal("100"), current_price=Decimal("98.995"),
            size=Decimal("1"), leverage=27, status="open",
            stop_loss=Decimal("99"), initial_stop_loss=Decimal("99"),
        )
        # Sample 1: shallow breach (0.005% beyond SL) -> episode starts, no fire.
        service._evaluate_breach_levels(pos, Decimal("98.995"), True, T0, ms)
        assert pos.breach_state and json.loads(pos.breach_state)["SL"]["fired"] is False
        # Sample 2: deep breach (1% beyond) -> bypass fires ON THE MUTATED STATE.
        # The old identity check dropped exactly this write (24x BCH re-fires).
        service._evaluate_breach_levels(pos, Decimal("98.0"), True, T0 + _td(seconds=6), ms)
        assert json.loads(pos.breach_state)["SL"]["fired"] is True


class TestGapHandling:
    def test_episode_survives_a_sampling_gap_while_still_beyond(self):
        # Mirrors NOTE/60's segmentation choice: no trade printing back inside
        # the level does not end the episode, even across a multi-second gap.
        state, _ = _step(None, 100.0, 99.9, is_long=True, t=T0)
        state, events = _step(state, 100.0, 99.8, is_long=True, t=T0 + timedelta(seconds=30))
        assert state is not None
        assert not any(e.kind == "started" for e in events)  # same episode, not a new one
