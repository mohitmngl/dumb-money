"""PHASE 2 tests: finalize_labels correctness (spec tests 7-9)."""
import unittest

import numpy as np

from dumbmoney import retest_config as cfg
from dumbmoney.retest_engine import finalize_labels, fold_symbol, wilders_atr
from tests.common import bar, dates, flat, hand, old_swing_scenario, ramp, run, series, spike


class TestLabels(unittest.TestCase):
    def test_07_mfe_mae_win(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = 60
        a = 1.2  # approximate ATR at crossing
        conf_line = 108.0 + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        # delay=3 touch without confirm, delay=4 confirm, delay=5 target
        blocks.append(flat(108.3, 2))  # delay=1,2 ignored touches
        blocks.append(hand(bar(108.5, 109.05, 107.25, 107.8)))  # delay=3 touch
        blocks.append(hand(bar(107.8, 108.35, 107.25, 108.0)))  # delay=4 confirm
        # huge close guarantees target hit regardless of exact signal_atr
        blocks.append(hand(bar(200.0, 200.0, 107.5, 200.0)))

        o, h, l, c, v = series(blocks)
        d = dates(len(c))
        r = fold_symbol(h, l, c, o, v, d, "US", "WIN")
        ev = [e for e in r.events if e.signal_date][0]
        atr = wilders_atr(h, l, c)
        events = finalize_labels([ev], h, l, c, atr)
        ev = events[0]

        self.assertEqual(ev.outcome, cfg.OutcomeClass.WIN.value)
        self.assertGreater(ev.mfe5, 0.0)
        self.assertLessEqual(ev.mae5, 0.0)
        self.assertEqual(ev.days_to_1atr, 1)

    def test_08_mfe_mae_stopped_out(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = 60
        a = 1.2
        conf_line = 108.0 + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        # delay=3 touch without confirm, delay=4 confirm, delay=5 stop hit
        blocks.append(flat(108.3, 2))  # delay=1,2 ignored touches
        blocks.append(hand(bar(108.5, 109.05, 107.25, 107.8)))  # delay=3 touch
        blocks.append(hand(bar(107.8, 108.35, 107.25, 108.0)))  # delay=4 confirm
        # extremely low low guarantees stop hit regardless of exact signal_atr
        blocks.append(hand(bar(108.0, 108.0, 0.0, 107.5)))  # delay=5 stop

        o, h, l, c, v = series(blocks)
        d = dates(len(c))
        r = fold_symbol(h, l, c, o, v, d, "US", "STOP")
        ev = [e for e in r.events if e.signal_date][0]
        atr = wilders_atr(h, l, c)
        events = finalize_labels([ev], h, l, c, atr)
        ev = events[0]

        self.assertEqual(ev.outcome, cfg.OutcomeClass.DEEP_DRAWDOWN.value)
        self.assertLessEqual(ev.mfe5, 0.5)
        self.assertLess(ev.mae5, 0.0)
        self.assertEqual(ev.days_to_1atr, -1)

    def test_09_days_to_1atr_timeout(self):
        blocks = old_swing_scenario(post_flat=4)
        crossing = 60
        a = 1.2
        conf_line = 108.0 + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        blocks.append(hand(bar(108.5, 109.05, 107.25, 107.8)))
        blocks.append(hand(bar(107.8, 108.35, 107.25, 108.0)))  # confirm
        # 25 bars of small range (no target, no stop)
        blocks.append(flat(108.0, 25))

        o, h, l, c, v = series(blocks)
        d = dates(len(c))
        r = fold_symbol(h, l, c, o, v, d, "US", "TIMEOUT")
        ev = [e for e in r.events if e.signal_date][0]
        atr = wilders_atr(h, l, c)
        events = finalize_labels([ev], h, l, c, atr)
        ev = events[0]

        self.assertEqual(ev.outcome, cfg.OutcomeClass.TIMEOUT.value)
        self.assertIsNone(ev.days_to_1atr)


if __name__ == "__main__":
    unittest.main()
