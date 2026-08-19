"""Unit tests for the breach persistence+bypass episode tracker (NOTE/64).

Pure-function tests: feed a sequence of (price, timestamp) samples through
evaluate_breach and check the events it emits. Thresholds mirror the
18-19/08 retrospective defaults (SL: 5s/0.15%, Smart SL: 900s/0.30%).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
        state, _ = _step(None, 100.0, 99.9, is_long=True, t=T0)
        state, events = _step(state, 100.0, 99.9, is_long=True, t=T0 + timedelta(seconds=6))
        assert any(e.kind == "rule_fired" for e in events)
        state, events2 = _step(state, 100.0, 99.9, is_long=True, t=T0 + timedelta(seconds=10))
        assert not any(e.kind == "rule_fired" for e in events2)

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


class TestGapHandling:
    def test_episode_survives_a_sampling_gap_while_still_beyond(self):
        # Mirrors NOTE/60's segmentation choice: no trade printing back inside
        # the level does not end the episode, even across a multi-second gap.
        state, _ = _step(None, 100.0, 99.9, is_long=True, t=T0)
        state, events = _step(state, 100.0, 99.8, is_long=True, t=T0 + timedelta(seconds=30))
        assert state is not None
        assert not any(e.kind == "started" for e in events)  # same episode, not a new one
