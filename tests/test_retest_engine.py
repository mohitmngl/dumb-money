"""PHASE 1 tests: causal pivot detection, zones, event state machine, quality
components (spec tests 1-6, 15, 16). Deterministic synthetic data only."""
import unittest

import numpy as np

from dumbmoney import retest_config as cfg
from dumbmoney.retest_engine import fold_symbol, wilders_atr
from tests.common import (atr_of, bar, confirm_scenario, dates, flat, hand,
                          old_swing_scenario, ramp, run, series, spike)

LEVEL = 108.0


def crossing_bar(blocks, pivot_idx=40, post_flat=4):
    """Bar index where the old_swing_scenario breakout ramp first closes above LEVEL.
    Zone created at pivot_idx, breakout requires age>=20 -> breakout at pivot_idx+20."""
    return pivot_idx + 20


# -------------------------------------------------------------------- helpers
def _warmup_and_spike(warmup=20, spike_high=120.0, descent_end=100.0, descent_bars=6):
    """Flat warmup -> spike -> descent. Creates zone at spike_high with inflated ATR."""
    blocks = [flat(100.0, warmup)]
    blocks.append(spike(spike_high, 100.0))
    blocks.append(ramp(spike_high - 4.0, descent_end, descent_bars))
    blocks.append(flat(descent_end, 4))
    return blocks


class TestCausalPivot(unittest.TestCase):
    def test_01_pivot_only_known_after_confirmation(self):
        blocks = old_swing_scenario(post_flat=4)
        pivot_idx = 40
        conf = pivot_idx + cfg.SWING_CONFIRMATION
        pre = run(blocks, symbol="PRE")
        o, h, l, c, v = series(blocks)
        d = dates(len(c))
        pre_trunc = fold_symbol(h, l, c, o, v, d, "US", "PRE")
        self.assertEqual(len(pre_trunc.zones), 1)
        full = run(blocks, symbol="FULL")
        self.assertEqual(len(full.zones), 1)
        self.assertEqual(full.zones[0].first_idx, pivot_idx)
        self.assertAlmostEqual(full.zones[0].level, LEVEL, delta=1e-9)

    def test_01b_no_zone_before_p_plus_confirmation(self):
        blocks = old_swing_scenario(post_flat=4)
        pivot_idx = 40
        conf = pivot_idx + cfg.SWING_CONFIRMATION
        o, h, l, c, v = series(blocks)
        d = dates(len(c))
        res = fold_symbol(h, l, c, o, v, d, "US", "T")
        res = fold_symbol(h[:conf], l[:conf], c[:conf], o[:conf], v[:conf], d[:conf], "US", "T")
        self.assertEqual(len(res.zones), 0)
        res2 = fold_symbol(h[:conf + 1], l[:conf + 1], c[:conf + 1], o[:conf + 1], v[:conf + 1], d[:conf + 1], "US", "T")
        self.assertEqual(len(res2.zones), 1)


class TestOldnessGate(unittest.TestCase):
    def test_02_age19_no_breakout_age20_breakout(self):
        blocks19 = old_swing_scenario(post_flat=3)
        r19 = run(blocks19, symbol="AGE19")
        self.assertEqual(len(r19.events), 0)
        self.assertEqual(len(r19.zones), 1)
        blocks20 = old_swing_scenario(post_flat=4)
        blocks20.append(flat(109.2, 2))  # 2 extra bars so stage can advance to WAITING_FOR_RETEST
        r20 = run(blocks20, symbol="AGE20")
        self.assertEqual(len(r20.events), 1)
        ev = r20.events[0]
        self.assertEqual(ev.breakout_idx, crossing_bar(old_swing_scenario(post_flat=4)))
        self.assertEqual(ev.age_at_breakout, 20)
        self.assertEqual(ev.stage, cfg.EventStage.WAITING_FOR_RETEST.value)


class TestEventIdentity(unittest.TestCase):
    def test_03_one_event_per_breakout_cycle(self):
        blocks = old_swing_scenario(post_flat=4)
        blocks.append(flat(109.5, 35))  # above hi_band -> no touch, stays WAITING_FOR_RETEST
        r = run(blocks, symbol="ONE")
        self.assertEqual(len(r.events), 1)
        ev = r.events[0]
        self.assertEqual(ev.event_id, "ONE:0:1")
        self.assertEqual(ev.stage, cfg.EventStage.WAITING_FOR_RETEST.value)


class TestBreakoutQuality(unittest.TestCase):
    def test_04_body_min(self):
        blocks = _warmup_and_spike()
        doji = bar(108.0, 109.1, 107.9, 108.0)   # body=0.01, ATR~8.42 -> body_min=0.421 -> FAIL
        blocks.append(hand(doji))
        r = run(blocks, symbol="DOJI")
        self.assertEqual(len(r.events), 0)

    def test_04b_close_location_min(self):
        blocks = _warmup_and_spike()
        wide = bar(108.0, 110.0, 108.0, 108.5)   # body=0.5 (passes body_min=0.421),
                                                   # close_location=0.05 (fails < 0.3)
        blocks.append(hand(wide))
        r = run(blocks, symbol="LOC")
        self.assertEqual(len(r.events), 0)

    def test_04c_valid_breakout(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = crossing_bar(blocks)
        a = atr_of(blocks, crossing) or 1.2
        good = bar(LEVEL - 0.5, LEVEL + 0.7, LEVEL - 0.65, LEVEL + 0.4)
        blocks.append(hand(good))
        r = run(blocks, symbol="GOOD")
        self.assertEqual(len(r.events), 1)
        ev = r.events[0]
        self.assertEqual(ev.breakout_idx, crossing)
        self.assertGreaterEqual(ev.breakout_body_atr, cfg.BREAKOUT_BODY_MIN_ATR)
        self.assertGreaterEqual(ev.breakout_close_location, cfg.BREAKOUT_CLOSE_LOCATION_MIN)


class TestZones(unittest.TestCase):
    def test_05_zone_ids_unique_and_join(self):
        blocks = [flat(100.0, 20)]
        highs = [105.0, 108.0, 111.0, 114.0, 117.0, 120.0, 123.0]
        base = 100.0
        for i, hp in enumerate(highs):
            blocks.append(spike(hp, base))
            blocks.append(flat(101.0, 8))
        blocks.append(spike(108.3, 101.0))
        blocks.append(flat(101.0, 10))
        r = run(blocks, symbol="Z7")
        ids = [z.id for z in r.zones]
        self.assertEqual(len(ids), 7)
        self.assertEqual(sorted(ids), list(range(7)))
        joined = [z for z in r.zones if abs(z.level - 108.0) < 0.6]
        self.assertEqual(len(joined), 1)
        self.assertEqual(len(joined[0].members), 2)


class TestRetestBounds(unittest.TestCase):
    def test_06a_touch_above_band_is_no_touch(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = crossing_bar(blocks)
        a = atr_of(blocks, crossing) or 1.2
        band_hi = LEVEL + cfg.RETEST_BOUND_HI_ATR * a
        hold = LEVEL + 3.0
        blocks.append(flat(hold, 85))
        r = run(blocks, symbol="NT")
        ev = r.events[0]
        self.assertEqual(ev.stage, cfg.EventStage.EXPIRED.value)
        self.assertEqual(ev.reason, "no_touch_80")
        self.assertEqual(ev.retest_idx, -1)

    def test_06b_early_touch_ignored(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = crossing_bar(blocks)
        a = atr_of(blocks, crossing) or 1.2
        band_hi = LEVEL + cfg.RETEST_BOUND_HI_ATR * a
        conf_line = LEVEL + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        # 2-bar ramp: bar1-2 early touches (delay 1,2 -> ignored);
        # bar3 delay=3 valid touch (close below confirm -> wait);
        # bar4 delay=4 close still below confirm -> window not expired yet
        blocks.append(ramp(LEVEL + 0.3, band_hi + 0.1, 2))  # early touches
        blocks.append(hand(bar(108.5, 109.05, 107.25, 107.8)))   # delay=3 touch, no confirm
        blocks.append(flat(107.8, 1))                 # window not expired yet
        r = run(blocks, symbol="ET")
        ev = r.events[0]
        self.assertEqual(ev.retest_idx, crossing + 3)
        self.assertEqual(ev.stage, cfg.EventStage.WAITING_FOR_CONFIRMATION.value)

    def test_06c_invalidation_after_retest(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = crossing_bar(blocks)
        a = atr_of(blocks, crossing) or 1.2
        inval = LEVEL + cfg.INVALIDATE_CLOSE_LEVEL_ATR * a
        # delay=1,2 ignored touches; delay=3 bar drops below invalidation (touches band but invalidates first)
        blocks.append(hand(bar(108.5, 109.05, 107.25, 107.8)))
        blocks.append(ramp(107.8, 106.5, 2))
        r = run(blocks, symbol="INV")
        ev = r.events[0]
        self.assertEqual(ev.stage, cfg.EventStage.INVALIDATED.value)
        self.assertEqual(ev.reason, "invalidated_wait")
        self.assertEqual(ev.retest_idx, -1)

    def test_06d_confirmation_fails_within_window(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = crossing_bar(blocks)
        a = atr_of(blocks, crossing) or 1.2
        conf_line = LEVEL + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        inval_line = LEVEL + cfg.INVALIDATE_CLOSE_LEVEL_ATR * a
        mid = (conf_line + inval_line) / 2.0
        # 2 bars above (ignored touches), then touch without confirm, then 4 bars no confirm -> FAILED
        blocks.append(flat(LEVEL + 0.4, 2))
        blocks.append(hand(bar(108.5, 109.05, 107.25, 107.8)))
        blocks.append(flat(107.8, 4))
        r = run(blocks, symbol="NC")
        ev = r.events[0]
        self.assertEqual(ev.stage, cfg.EventStage.FAILED.value)
        self.assertEqual(ev.reason, "no_confirmation")
        self.assertFalse(ev.signal_date)

    def test_06e_confirmation_same_candle(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = crossing_bar(blocks)
        a = atr_of(blocks, crossing) or 1.2
        conf_line = LEVEL + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        # 2-bar ramp: bar1 touches band (delay too short), bar2 touches+confirms
        # -> SIGNAL_GENERATED; then 2 flat bars -> window expires as FAILED
        blocks.append(flat(LEVEL + 0.4, 2))
        blocks.append(ramp(LEVEL + 0.4, conf_line + 0.15, 2))
        blocks.append(flat(conf_line + 0.15, 2))
        r = run(blocks, symbol="SC")
        ev = r.events[0]
        self.assertEqual(ev.stage, cfg.EventStage.SIGNAL_GENERATED.value)
        self.assertEqual(ev.confirm_idx, crossing + 3)
        self.assertTrue(ev.signal_date)


class TestQualityComponents(unittest.TestCase):
    def test_15_clean_retest_shallower_than_loose(self):
        blocks_c = old_swing_scenario(post_flat=4)
        crossing_c = crossing_bar(blocks_c)
        a = atr_of(blocks_c, crossing_c) or 1.2
        conf_line = LEVEL + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        # clean: shallow touch + same-bar confirm
        blocks_c.append(flat(LEVEL + 0.4, 2))
        blocks_c.append(hand(bar(108.5, 109.05, 107.85, 108.0)))
        blocks_c.append(flat(108.0, 3))
        r_c = run(blocks_c, symbol="CLEAN")
        ev_c = [e for e in r_c.events if e.signal_date][0]

        blocks_l = old_swing_scenario(post_flat=4)
        crossing_l = crossing_bar(blocks_l)
        inval_line = LEVEL + cfg.INVALIDATE_CLOSE_LEVEL_ATR * a
        deep = (inval_line + conf_line) / 2.0
        # loose: deep touch (delay=3), then confirm on next bar
        blocks_l.append(flat(LEVEL + 0.4, 2))
        blocks_l.append(hand(bar(108.5, 109.05, 107.0, 107.5)))
        blocks_l.append(ramp(107.5, conf_line + 0.05, 2))
        blocks_l.append(flat(conf_line + 0.05, 3))
        r_l = run(blocks_l, symbol="LOOSE")
        ev_l = [e for e in r_l.events if e.signal_date][0]

        self.assertTrue(ev_c.signal_date and ev_l.signal_date)
        self.assertLess(ev_c.retest_depth_atr, ev_l.retest_depth_atr)
        self.assertGreater(ev_l.retest_low_atr, ev_c.retest_low_atr)


class TestLadderNoCurrentSetup(unittest.TestCase):
    def test_16_far_away_levels_give_null_scores(self):
        # Zones created by spike-and-descent at far-away levels (340..120, descending).
        # Longer warmup ensures ATR is valid at first pivot.
        # Price stays well below all zone levels, so no breakouts occur.
        blocks = [flat(100.0, 25)]
        for hp in [340.0, 300.0, 260.0, 230.0, 190.0, 150.0, 120.0]:
            blocks.append(spike(hp, 100.0))
            blocks.append(ramp(hp - 4.0, 100.0, 6))
            blocks.append(flat(101.0, 15))
        blocks.append(flat(101.0, 40))
        r = run(blocks, symbol="LAD")
        self.assertGreaterEqual(len(r.zones), 1)
        self.assertEqual(len(r.events), 0)
        self.assertTrue(np.isnan(r.current_scores).all())
        self.assertTrue(all(s == "NO_SETUP" for s in r.states))


if __name__ == "__main__":
    unittest.main()
