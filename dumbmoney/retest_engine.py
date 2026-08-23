"""Causal old-swing-high retest engine (replaces the legacy BUG-laden implementation).

Design contract (RETEST_AUDIT.md / spec):
- Deterministic left-to-right fold: state at bar t depends only on bars <= t.
- Swing pivots are known at p + SWING_CONFIRMATION (causal).
- Zones are clusters of confirmed swing highs within ZONE_CLUSTER_ATR of the level;
  zone level = prominence-weighted mean of member pivot prices. Membership is
  cumulative (members confirmed <= t), so the level at any date depends only on
  bars <= that date -> prefix-invariant (spec test 17).
- Event state machine: BREAKOUT_CONFIRMED -> WAITING_FOR_RETEST -> (touch)
  -> WAITING_FOR_CONFIRMATION -> SIGNAL_GENERATED (close-entry) -> outcome.
  Barriers are evaluated in-fold per bar (causal at bar close):
  target close >= entry + 2.0*SIGNAL_ATR, stop low <= entry - 0.75*SIGNAL_ATR,
  20-candle time barrier. Same-candle target+stop resolves STOPPED_OUT
  (conservative drawdown-first). Invalidation (close < level - 0.60 ATR) applies
  only before a signal; once in the trade the barriers govern (documented).
- Per-bar visible score = ORIGINAL (frozen at confirmation) decayed by the spec-O
  distance and time freshness tables; NULL (NaN) whenever no confirmed signal is
  actively unresolved, and from the resolution bar onward.
- Model scoring: when a trained CatBoost model is loaded, original_score is the
  model probability * 100. When no model is loaded, original_score is None and
  scores stay NULL (structure-only mode).
- Labels (MFE/MAE/days) are computed post-fold by finalize_labels() using the
  same barriers; they use future bars by design (labels, not features).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
import os
import logging

import numpy as np

import dumbmoney.retest_config as cfg

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- ATR
def wilders_atr(high, low, close, period=cfg.ATR_PERIOD):
    """Wilder ATR(period). First valid value at index `period-1` (mean of the first
    `period` TRs), then Wilder smoothing."""
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    n = len(close)
    if n < period + 1:
        return np.full(n, np.nan)
    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.full(n, np.nan)
    atr[period - 1] = tr[:period].mean()
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def _rolling_mean(values, window):
    v = np.asarray(values, dtype=np.float64)
    n = len(v)
    out = np.full(n, np.nan)
    if n == 0 or window <= 0:
        return out
    cs = np.cumsum(np.concatenate([[0.0], v]))
    for i in range(n):
        lo = max(0, i - window + 1)
        out[i] = (cs[i + 1] - cs[lo]) / (i - lo + 1)
    return out


# ------------------------------------------------------------------- freshness
def freshness_distance(close_dist_atr):
    """abs((close - level)/SIGNAL_ATR) -> freshness factor (spec O). None = exhausted."""
    d = abs(close_dist_atr)
    for boundary, fresh in cfg.FRESHNESS_DISTANCE:
        if d <= boundary:
            return fresh
    return None


def freshness_time(candles_since_confirm):
    """candles since confirmation -> freshness factor (spec O). None = exhausted."""
    for boundary, fresh in cfg.FRESHNESS_TIME:
        if candles_since_confirm <= boundary:
            return fresh
    return None


# ----------------------------------------------------------------------- pivots
@dataclass
class Pivot:
    idx: int
    date: str
    price: float
    kind: str  # 'H' swing high, 'L' swing low
    prominence_atr: Optional[float] = None


@dataclass
class Zone:
    id: int
    symbol: str
    market: str
    members: list[Pivot] = field(default_factory=list)
    cycle_seq: int = 0
    cycle: Optional["EventCycle"] = None
    reactions: int = 0
    false_breakouts: int = 0
    exhausted: bool = False
    last_probe_idx: int = -10

    @property
    def first_idx(self):
        return self.members[0].idx

    @property
    def last_idx(self):
        return self.members[-1].idx

    @property
    def level(self):
        """Prominence-weighted mean of member pivot prices (members confirmed <= t)."""
        w = np.array([m.prominence_atr for m in self.members], dtype=np.float64)
        p = np.array([m.price for m in self.members], dtype=np.float64)
        return float(np.average(p, weights=w))

    @property
    def prominence_atr(self):
        return max((m.prominence_atr or 0.0) for m in self.members)

    @property
    def width_sessions(self):
        return self.last_idx - self.first_idx

    @property
    def width_atr(self):
        lo = min(m.price for m in self.members)
        hi = max(m.price for m in self.members)
        base = self.members[-1].prominence_atr or 1.0
        return (hi - lo) / base if base > 0 else 0.0

    def age(self, t):
        return t - self.first_idx


# ----------------------------------------------------------------------- events
@dataclass
class EventCycle:
    zone_id: int
    seq: int
    event_id: str
    stage: str = cfg.EventStage.BREAKOUT_CONFIRMED.value

    breakout_idx: int = -1
    breakout_date: str = ""
    breakout_close: float = np.nan
    breakout_level: float = np.nan  # frozen zone level at breakout (prefix-invariant)
    breakout_atr: float = np.nan
    breakout_body_atr: float = np.nan
    breakout_close_location: float = np.nan
    breakout_gap_atr: float = np.nan
    breakout_volume_ratio: float = np.nan
    breakout_consecutive_closes: int = 0
    breakout_prior_close_rel: float = np.nan
    breakout_retreat_within_3: int = 0

    retest_idx: int = -1
    retest_date: str = ""
    retest_atr: float = np.nan
    retest_low_atr: float = np.nan
    retest_volume_ratio: float = np.nan
    retest_depth_atr: float = np.nan
    retest_touch_candles: int = 0
    retest_closes_below_level: int = 0
    confirm_close_location: float = np.nan
    retest_window_end: int = -1

    confirm_idx: int = -1
    confirm_date: str = ""
    signal_date: str = ""
    entry: float = np.nan
    signal_atr: float = np.nan
    age_at_breakout: int = -1
    age_band: int = -1

    trend_higher_highs: int = 0
    context_pivot_low_dist_atr: float = np.nan
    sma20_slope_atr: float = np.nan
    sma20_above_sma60: int = 0
    median_traded_value: float = np.nan

    original_score: Optional[float] = None
    model_version: str = cfg.MODEL_VERSION
    model_used: bool = False

    resolution_idx: int = -1
    resolution_date: str = ""
    outcome: Optional[str] = None
    reason: str = ""
    censored: bool = False

    mfe5: float = np.nan
    mfe10: float = np.nan
    mfe20: float = np.nan
    mae5: float = np.nan
    mae10: float = np.nan
    mae20: float = np.nan
    days_to_1atr: Optional[int] = None
    days_to_target: Optional[int] = None
    days_to_stop: Optional[int] = None

    def as_dict(self):
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = None if np.isnan(v) else v
        return d


def _cycle_from_dict(d):
    c = EventCycle(d["zone_id"], d["seq"], d["event_id"])
    for k in asdict(c):
        if k in d:
            setattr(c, k, d[k])
    return c


@dataclass
class FoldState:
    market: str
    symbol: str
    zones: list[Zone] = field(default_factory=list)
    swings_high: list[Pivot] = field(default_factory=list)
    swings_low: list[Pivot] = field(default_factory=list)
    events: list[EventCycle] = field(default_factory=list)
    next_zone_id: int = 0
    watermark: int = -1

    def to_dict(self):
        return {"market": self.market, "symbol": self.symbol, "next_zone_id": self.next_zone_id,
                "watermark": self.watermark,
                "zones": [{"id": z.id, "symbol": z.symbol, "market": z.market,
                           "members": [m.__dict__ for m in z.members], "cycle_seq": z.cycle_seq,
                           "cycle": z.cycle.as_dict() if z.cycle else None,
                           "reactions": z.reactions, "false_breakouts": z.false_breakouts,
                           "exhausted": z.exhausted, "last_probe_idx": z.last_probe_idx}
                          for z in self.zones],
                "swings_high": [m.__dict__ for m in self.swings_high],
                "swings_low": [m.__dict__ for m in self.swings_low],
                "events": [e.as_dict() for e in self.events]}

    @classmethod
    def from_dict(cls, d):
        st = cls(d["market"], d["symbol"])
        st.next_zone_id = d["next_zone_id"]
        st.watermark = d["watermark"]
        st.swings_high = [Pivot(m["idx"], m["date"], m["price"], m["kind"], m.get("prominence_atr")) for m in d["swings_high"]]
        st.swings_low = [Pivot(m["idx"], m["date"], m["price"], m["kind"], m.get("prominence_atr")) for m in d["swings_low"]]
        st.events = [_cycle_from_dict(e) for e in d["events"]]
        for z in d["zones"]:
            zn = Zone(z["id"], z["symbol"], z["market"])
            zn.members = [Pivot(m["idx"], m["date"], m["price"], m["kind"], m.get("prominence_atr")) for m in z["members"]]
            zn.cycle_seq = z["cycle_seq"]
            zn.cycle = _cycle_from_dict(z["cycle"]) if z["cycle"] else None
            zn.reactions = z["reactions"]
            zn.false_breakouts = z["false_breakouts"]
            zn.exhausted = z["exhausted"]
            zn.last_probe_idx = z["last_probe_idx"]
            st.zones.append(zn)
        return st


@dataclass
class FoldResult:
    market: str
    symbol: str
    dates: list
    current_scores: np.ndarray
    original_scores: np.ndarray
    states: list
    zones: list
    events: list
    watermark: int
    model_used: bool
    model_version: str


def _pick_visible(a, b):
    """Deterministic best-visible selection between two (score, orig, state) tuples."""
    if a is None:
        return b
    if b is None:
        return a
    if not np.isnan(a[0]) and not np.isnan(b[0]):
        return a if a[0] > b[0] else b
    if not np.isnan(a[0]):
        return a
    if not np.isnan(b[0]):
        return b
    priority = {cfg.EventStage.SIGNAL_GENERATED.value: 4, cfg.EventStage.WAITING_FOR_CONFIRMATION.value: 3,
                cfg.EventStage.WAITING_FOR_RETEST.value: 2, cfg.EventStage.BREAKOUT_CONFIRMED.value: 1}
    return a if priority.get(a[2], 0) >= priority.get(b[2], 0) else b


# ----------------------------------------------------------------------- engine
class RetestEngine:
    """Causal fold for one symbol. fold(initial_state=...) resumes from a watermark."""

    def __init__(self, market, symbol, score_fn: Optional[Callable[[EventCycle, list], Optional[float]]] = None):
        self.market = market
        self.symbol = symbol
        self.score_fn = score_fn
        self.state = FoldState(market, symbol)

    # ------------------------------------------------------------- public fold
    def fold(self, dates, open_, high, low, close, volume, initial_state=None, start_idx=0):
        n = len(close)
        empty = FoldResult(self.market, self.symbol, list(dates), np.full(n, np.nan),
                           np.full(n, np.nan), ["NO_SETUP"] * n, [], [], n - 1,
                           self.score_fn is not None, cfg.MODEL_VERSION)
        if n < cfg.SWING_LOOKBACK + cfg.SWING_CONFIRMATION + 2:
            return empty
        if initial_state is not None:
            self.state = initial_state
        elif start_idx == 0:
            self.state = FoldState(self.market, self.symbol)

        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        open_ = np.asarray(open_, dtype=np.float64)
        volume = np.asarray(volume, dtype=np.float64)
        atr = wilders_atr(high, low, close)
        sma20 = _rolling_mean(close, 20)
        sma60 = _rolling_mean(close, 60)
        vol20 = _rolling_mean(volume, 20)

        current = np.full(n, np.nan)
        original = np.full(n, np.nan)
        state_strs = ["NO_SETUP"] * n

        for t in range(start_idx, n):
            p = t - cfg.SWING_CONFIRMATION
            if p >= cfg.SWING_LOOKBACK and p < n:
                self._confirm_swing_high(high, low, atr, dates, p)
                self._confirm_swing_low(high, low, atr, dates, p)
            best = self._advance_cycles(high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t)
            if best is not None:
                current[t], original[t], state_strs[t] = best
        self.state.watermark = n - 1
        self._finalize_breakout_retreats(close)
        return FoldResult(self.market, self.symbol, list(dates), current, original, state_strs,
                          list(self.state.zones), list(self.state.events), n - 1,
                          self.score_fn is not None, cfg.MODEL_VERSION)

    def resume_start(self):
        return self.state.watermark + 1

    # ------------------------------------------------------------------ swings
    def _confirm_swing_high(self, high, low, atr, dates, p):
        if p < cfg.SWING_LOOKBACK:
            return
        left = high[p - cfg.SWING_LOOKBACK:p]
        right = high[p + 1:p + 1 + cfg.SWING_CONFIRMATION]
        if len(right) < cfg.SWING_CONFIRMATION:
            return
        if high[p] > left.max() and high[p] > right.max():
            lv = low[p - cfg.SWING_LOOKBACK:p].min()
            rv = low[p + 1:p + 1 + cfg.SWING_CONFIRMATION].min()
            prom = high[p] - max(lv, rv)
            prom_atr = (prom / atr[p]) if not np.isnan(atr[p]) else None
            piv = Pivot(p, dates[p], float(high[p]), "H", float(prom_atr) if prom_atr is not None else None)
            self.state.swings_high.append(piv)
            if len(self.state.swings_high) > 80:
                del self.state.swings_high[0]
            if prom_atr is not None and prom_atr >= cfg.MIN_PROMINENCE_ATR:
                self._zone_worthy_pivot(piv, atr[p])

    def _confirm_swing_low(self, high, low, atr, dates, p):
        if p < cfg.SWING_LOOKBACK:
            return
        left = low[p - cfg.SWING_LOOKBACK:p]
        right = low[p + 1:p + 1 + cfg.SWING_CONFIRMATION]
        if len(right) < cfg.SWING_CONFIRMATION:
            return
        if low[p] < left.min() and low[p] < right.min():
            piv = Pivot(p, dates[p], float(low[p]), "L", None)
            self.state.swings_low.append(piv)
            if len(self.state.swings_low) > 80:
                del self.state.swings_low[0]

    def _zone_worthy_pivot(self, piv: Pivot, atr_now):
        best, best_d = None, None
        for z in self.state.zones:
            if z.exhausted:
                continue
            d = abs(z.level - piv.price)
            if d <= cfg.ZONE_CLUSTER_ATR * atr_now and (best is None or d < best_d):
                best, best_d = z, d
        if best is not None:
            best.members.append(piv)
        else:
            z = Zone(self.state.next_zone_id, self.symbol, self.market, [piv])
            self.state.next_zone_id += 1
            self.state.zones.append(z)

    # -------------------------------------------------------------- per-bar pass
    def _advance_cycles(self, high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t):
        a = atr[t]
        best_visible = None
        for z in self.state.zones:
            if z.exhausted:
                continue
            lvl = z.level
            cycle = z.cycle
            if cycle is None:
                if z.age(t) >= cfg.MIN_LEVEL_AGE_AT_BREAKOUT and \
                        close[t] >= lvl + cfg.BREAKOUT_LEVEL_TOUCH_ATR * a and \
                        (t == 0 or close[t - 1] < lvl) and \
                        self._breakout_quality(open_, high, low, close, t, a):
                    cycle = self._start_cycle(z, high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t)
                    best_visible = _pick_visible(best_visible, (np.nan, np.nan, cycle.stage))
                else:
                    self._count_reactions(z, high, low, close, atr, t, lvl)
                continue
            terminal, vis = self._advance_cycle(cycle, z, high, low, close, volume, atr, sma20, sma60, vol20, dates, t)
            if vis is not None:
                best_visible = _pick_visible(best_visible, vis)
            if terminal:
                z.cycle = None
        return best_visible

    def _count_reactions(self, z, high, low, close, atr, t, lvl):
        a = atr[t]
        if np.isnan(a) or a <= 0:
            return
        lo_band = lvl + cfg.RETEST_BOUND_LO_ATR * a
        hi_band = lvl + cfg.CONFIRM_CLOSE_LEVEL_ATR * a
        if lo_band <= close[t] < hi_band and high[t] >= hi_band and t - z.last_probe_idx >= 2:
            z.reactions += 1
            z.last_probe_idx = t

    def _breakout_quality(self, open_, high, low, close, t, a):
        if np.isnan(a) or a <= 0:
            return False
        body = abs(close[t] - open_[t]) / a
        rng = high[t] - low[t]
        loc = (close[t] - low[t]) / rng if rng > 0 else 1.0
        return body >= cfg.BREAKOUT_BODY_MIN_ATR and loc >= cfg.BREAKOUT_CLOSE_LOCATION_MIN

    def _start_cycle(self, z, high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t):
        z.cycle_seq += 1
        c = EventCycle(z.id, z.cycle_seq, f"{self.symbol}:{z.id}:{z.cycle_seq}")
        c.breakout_idx = t
        c.breakout_date = dates[t]
        c.breakout_close = float(close[t])
        c.breakout_level = float(z.level)
        c.breakout_atr = float(atr[t])
        c.breakout_body_atr = abs(close[t] - open_[t]) / atr[t]
        rng = high[t] - low[t]
        c.breakout_close_location = (close[t] - low[t]) / rng if rng > 0 else 1.0
        c.breakout_gap_atr = (open_[t] - close[t - 1]) / atr[t] if t > 0 else 0.0
        c.breakout_volume_ratio = volume[t] / vol20[t] if not np.isnan(vol20[t]) and vol20[t] > 0 else np.nan
        c.breakout_prior_close_rel = (close[t - 1] - z.level) / atr[t] if t > 0 else 0.0
        cc = 0
        for i in range(t, max(-1, t - 25), -1):
            if close[i] >= z.level + cfg.CONFIRM_CLOSE_LEVEL_ATR * atr[i]:
                cc += 1
            else:
                break
        c.breakout_consecutive_closes = min(cc, 20)
        c.age_at_breakout = z.age(t)
        c.age_band = self._age_band(c.age_at_breakout)
        recent_highs = [s for s in self.state.swings_high if s.idx <= t]
        hh = 0
        for i in range(1, len(recent_highs)):
            if recent_highs[i].price >= recent_highs[i - 1].price:
                hh += 1
        c.trend_higher_highs = hh
        if self.state.swings_low:
            c.context_pivot_low_dist_atr = (close[t] - self.state.swings_low[-1].price) / atr[t]
        c.sma20_slope_atr = ((sma20[t] - sma20[t - 5]) / atr[t]) if t >= 5 and not np.isnan(sma20[t]) and not np.isnan(sma20[t - 5]) else np.nan
        c.sma20_above_sma60 = 1 if (not np.isnan(sma20[t]) and not np.isnan(sma60[t]) and sma20[t] > sma60[t]) else 0
        lo = max(0, t - 19)
        tv = close[lo:t + 1] * volume[lo:t + 1]
        c.median_traded_value = float(np.median(tv)) if len(tv) else np.nan
        c.stage = cfg.EventStage.BREAKOUT_CONFIRMED.value
        z.cycle = c
        self.state.events.append(c)
        return c

    def _age_band(self, age):
        for i, (lo, hi) in enumerate(cfg.AGE_BANDS):
            if lo <= age <= hi:
                return i
        return -1

    # ------------------------------------------------------------ cycle machine
    def _advance_cycle(self, c, z, high, low, close, volume, atr, sma20, sma60, vol20, dates, t):
        lvl = c.breakout_level
        a = atr[t]
        st = c.stage
        if np.isnan(a):
            return False, (np.nan, np.nan, st)

        if st == cfg.EventStage.BREAKOUT_CONFIRMED.value:
            if t == c.breakout_idx:
                return False, (np.nan, np.nan, st)
            c.stage = cfg.EventStage.WAITING_FOR_RETEST.value
            return False, (np.nan, np.nan, c.stage)

        if st == cfg.EventStage.WAITING_FOR_RETEST.value:
            if close[t] < lvl + cfg.INVALIDATE_CLOSE_LEVEL_ATR * a:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.INVALIDATED.value, "invalidated_wait")
            delay = t - c.breakout_idx
            if delay > cfg.RETEST_DELAY_MAX:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.EXPIRED.value, "no_touch_80")
            if delay >= cfg.RETEST_DELAY_MIN and low[t] <= lvl + cfg.RETEST_BOUND_HI_ATR * a:
                c.retest_idx = t
                c.retest_date = dates[t]
                c.retest_atr = a
                c.retest_low_atr = (lvl - low[t]) / a
                c.retest_volume_ratio = volume[t] / vol20[t] if not np.isnan(vol20[t]) and vol20[t] > 0 else np.nan
                c.retest_touch_candles = 1
                c.retest_window_end = t + cfg.CONFIRM_WINDOW
                if close[t] >= lvl + cfg.CONFIRM_CLOSE_LEVEL_ATR * a:
                    self._confirm(c, z, t, dates[t], a, high, low, close)
                else:
                    c.stage = cfg.EventStage.WAITING_FOR_CONFIRMATION.value
            return False, (np.nan, np.nan, c.stage)

        if st == cfg.EventStage.WAITING_FOR_CONFIRMATION.value:
            if close[t] < lvl + cfg.INVALIDATE_CLOSE_LEVEL_ATR * a:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.INVALIDATED.value, "invalidated_retest")
            if close[t] >= lvl + cfg.CONFIRM_CLOSE_LEVEL_ATR * a:
                self._confirm(c, z, t, dates[t], a, high, low, close)
                entry = c.entry
                sa = c.signal_atr
                hit_stop = low[t] <= entry + cfg.BARRIER_DOWN_ATR * sa
                hit_target = close[t] >= entry + cfg.BARRIER_UP_ATR * sa
                if hit_stop and hit_target:
                    return self._terminate(c, z, t, dates[t], cfg.EventStage.STOPPED_OUT.value, "same_candle_conservative")
                if hit_stop:
                    return self._terminate(c, z, t, dates[t], cfg.EventStage.STOPPED_OUT.value, "barrier_stop")
                if hit_target:
                    return self._terminate(c, z, t, dates[t], cfg.EventStage.TARGET_REACHED.value, "barrier_target")
                return False, self._visible(c, z, close, t)
            if low[t] <= lvl + cfg.RETEST_BOUND_HI_ATR * a:
                c.retest_touch_candles += 1
            if close[t] < lvl + cfg.CONFIRM_CLOSE_LEVEL_ATR * a:
                c.retest_closes_below_level += 1
            if t > c.retest_window_end:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.FAILED.value, "no_confirmation")
            return False, (np.nan, np.nan, c.stage)

        if st == cfg.EventStage.SIGNAL_GENERATED.value:
            entry = c.entry
            sa = c.signal_atr
            hit_stop = low[t] <= entry + cfg.BARRIER_DOWN_ATR * sa
            hit_target = close[t] >= entry + cfg.BARRIER_UP_ATR * sa
            if hit_stop and hit_target:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.STOPPED_OUT.value, "same_candle_conservative")
            if hit_stop:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.STOPPED_OUT.value, "barrier_stop")
            if hit_target:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.TARGET_REACHED.value, "barrier_target")
            if t - c.confirm_idx >= cfg.TIME_BARRIER:
                return self._terminate(c, z, t, dates[t], cfg.EventStage.EXPIRED.value, "timeout_20")
            return False, self._visible(c, z, close, t)
        return False, None

    def _confirm(self, c, z, t, date, atr_now, high, low, close):
        c.confirm_idx = t
        c.confirm_date = date
        c.signal_date = date
        c.entry = float(close[t])
        c.signal_atr = float(atr_now)
        c.stage = cfg.EventStage.SIGNAL_GENERATED.value
        rng = high[t] - low[t]
        c.confirm_close_location = (close[t] - low[t]) / rng if rng > 0 else 1.0
        if c.retest_idx >= 0:
            c.retest_depth_atr = (c.breakout_level - float(low[c.retest_idx:t + 1].min())) / c.signal_atr
            c.retest_closes_below_level = int(np.sum(
                 (close[c.retest_idx:t + 1] < c.breakout_level + cfg.CONFIRM_CLOSE_LEVEL_ATR * c.signal_atr).astype(int)))
        c.original_score = self.score_fn(c, self.state.zones) if self.score_fn is not None else None
        c.model_used = c.original_score is not None

    def _terminate(self, c, z, t, date, stage, reason):
        c.stage = stage
        c.reason = reason
        c.resolution_idx = t
        c.resolution_date = date
        if stage in (cfg.EventStage.INVALIDATED.value, cfg.EventStage.EXPIRED.value, cfg.EventStage.FAILED.value):
            z.false_breakouts += 1
        if stage == cfg.EventStage.TARGET_REACHED.value:
            z.exhausted = True
        return True, (np.nan, np.nan, stage)

    def _visible(self, c, z, close, t):
        if c.stage != cfg.EventStage.SIGNAL_GENERATED.value:
            return (np.nan, np.nan, c.stage)
        d_atr = (close[t] - c.breakout_level) / c.signal_atr
        fd = freshness_distance(d_atr)
        ft = freshness_time(t - c.confirm_idx)
        cur = (c.original_score * fd * ft) if (c.original_score is not None and fd is not None and ft is not None) else np.nan
        orig = c.original_score if c.original_score is not None else np.nan
        return (cur, orig, c.stage)

    def _finalize_breakout_retreats(self, close):
        for c in self.state.events:
            if c.breakout_idx >= 0:
                end = min(c.breakout_idx + 4, len(close))
                if end > c.breakout_idx + 1:
                    c.breakout_retreat_within_3 = int(np.any(
                        close[c.breakout_idx + 1:end] < c.breakout_level + cfg.CONFIRM_CLOSE_LEVEL_ATR * c.breakout_atr))
                else:
                    c.breakout_retreat_within_3 = 0


# ==============================================================================
# Public API (single implementation used by stats, historical, training, API)
# ==============================================================================
def fold_symbol(high, low, close, open_, volume, dates, market, symbol,
                score_fn=None, initial_state=None, start_idx=0):
    """Causal fold for one symbol. Returns FoldResult (arrays aligned to input)."""
    eng = RetestEngine(market, symbol, score_fn)
    if initial_state is not None:
        eng.state = initial_state
        if start_idx == 0:
            start_idx = initial_state.watermark + 1
    return eng.fold(dates, open_, high, low, close, volume, initial_state, start_idx)


def fold_symbol_frame(df, market, symbol, score_fn=None, initial_state=None, start_idx=0):
    """DataFrame variant: requires columns date,open,high,low,close,volume."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    volume = df["volume"].to_numpy(dtype=float)
    dates = [str(d) for d in df["date"].tolist()]
    return fold_symbol(high, low, close, open_, volume, dates, market, symbol,
                       score_fn=score_fn, initial_state=initial_state, start_idx=start_idx)


def finalize_labels(events, high, low, close, atr, dates=None):
    """Post-fold label computation for training (uses future bars by design).

    Fills MFE/MAE over fixed windows [1..k] from the confirmation bar and the
    signed days-to-first-1-ATR excursion. Resolution itself is determined in-fold
    (identical barriers); this pass only adds windowed excursions and dates.
    """
    events = [e for e in events if e.confirm_idx >= 0 and e.signal_date]
    for c in events:
        if np.isnan(c.entry) or np.isnan(c.signal_atr) or c.signal_atr <= 0:
            continue
        if c.outcome is None:
            c.outcome = (cfg.OutcomeClass.WIN.value if c.stage == cfg.EventStage.TARGET_REACHED.value else
                         cfg.OutcomeClass.DEEP_DRAWDOWN.value if c.stage == cfg.EventStage.STOPPED_OUT.value else
                         cfg.OutcomeClass.TIMEOUT.value)
        entry = c.entry
        sa = c.signal_atr
        end = min(c.confirm_idx + 1 + cfg.TIME_BARRIER, len(close))
        for k in cfg.MFE_MAE_WINDOWS:
            wend = min(c.confirm_idx + 1 + k, len(close))
            if wend > c.confirm_idx + 1:
                win_h = high[c.confirm_idx + 1:wend]
                win_l = low[c.confirm_idx + 1:wend]
                setattr(c, f"mfe{k}", float((win_h.max() - entry) / sa))
                setattr(c, f"mae{k}", float((win_l.min() - entry) / sa))
        for i in range(c.confirm_idx + 1, end):
            up = high[i] >= entry + cfg.DAYS_1ATR * sa
            dn = low[i] <= entry - cfg.DAYS_1ATR * sa
            if up and dn:
                c.days_to_1atr = -(i - c.confirm_idx)
                break
            if up:
                c.days_to_1atr = i - c.confirm_idx
                break
            if dn:
                c.days_to_1atr = -(i - c.confirm_idx)
                break
    return events


def current_status(result: FoldResult):
    """Diagnostics for the latest completed bar (used by stats and detail endpoint)."""
    t = result.watermark
    if t < 0:
        return {"status": "DATA_INSUFFICIENT", "score": None, "state": "NO_SETUP"}
    score = result.current_scores[t]
    active = [c for c in result.events if c.stage == cfg.EventStage.SIGNAL_GENERATED.value]
    if active:
        best = active[-1]
        for c in active:
            if (c.original_score or 0.0) > (best.original_score or 0.0):
                best = c
        status = "VALID" if (score is not None and not np.isnan(score)) else "MODEL_UNAVAILABLE"
        return {"status": status, "score": (None if score is None or np.isnan(score) else round(float(score), 4)),
                "state": result.states[t], "event_id": best.event_id,
                "original_score": best.original_score, "entry": best.entry, "signal_atr": best.signal_atr,
                "level": best.breakout_level}
    return {"status": "NO_SETUP", "score": None, "state": result.states[t]}


# ==============================================================================
# Public API: compute_retest_score_for_symbol / compute_retest_score_current
# ==============================================================================

def compute_retest_score_for_symbol(grp, model=None):
    """Compute OLD_SWING_RETEST_SCORE for a single symbol's full history.

    Returns a pandas Series indexed by the input date index, with NaN where
    no active (unresolved) signal is present and NULL where the engine has
    not reached a state where a score is meaningful.
    """
    import pandas as pd

    if len(grp) < 60:
        return pd.Series(np.nan, index=grp.index)

    grp = grp.sort_values("date").reset_index(drop=True)
    dates = grp["date"].astype(str).tolist()
    o = grp["open"].astype(float).values
    h = grp["high"].astype(float).values
    l = grp["low"].astype(float).values
    c = grp["close"].astype(float).values
    v = grp["volume"].astype(float).values

    atr = wilders_atr(h, l, c)

    try:
        result = fold_symbol(h, l, c, o, v, dates, grp.get("market", "US")[0] if "market" in grp.columns else "US",
                             grp.get("symbol", "UNKNOWN")[0] if "symbol" in grp.columns else "UNKNOWN")
    except Exception:
        return pd.Series(np.nan, index=grp.index)

    n = len(c)
    scores = np.full(n, np.nan, dtype=np.float64)

    for i in range(n):
        s = result.current_scores[i]
        if s is not None and not np.isnan(s):
            scores[i] = s

    return pd.Series(scores, index=grp.index)


def compute_retest_score_current(grp, model=None):
    """Compute OLD_SWING_RETEST_SCORE for current mode (last bar only).

    Returns a single float (0-100) or np.nan when no active retest is present.
    """
    series = compute_retest_score_for_symbol(grp, model)
    if series is None or len(series) == 0:
        return np.nan
    val = series.iloc[-1]
    return val if not np.isnan(val) else np.nan


# ==============================================================================
# MODEL INTEGRATION — CatBoost model loading and feature extraction
# ==============================================================================

# Module-level singleton for the trained model
_MODEL = None
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "retest_v1", "model.cbm")

# 29 feature columns matching the trained model
FEATURE_COLUMNS = [
    "breakout_body_atr", "breakout_close_location", "breakout_gap_atr",
    "breakout_volume_ratio", "breakout_consecutive_closes",
    "breakout_prior_close_rel", "breakout_retreat_within_3", "breakout_age_at",
    "retest_low_atr", "retest_depth_atr", "retest_touch_candles",
    "retest_closes_below_level", "retest_volume_ratio",
    "zone_prominence_atr", "zone_width_atr", "zone_reactions", "zone_false_breakouts",
    "age_band", "trend_higher_highs", "context_pivot_low_dist_atr",
    "sma20_slope_atr", "sma20_above_sma60", "median_traded_value_log",
    "entry", "signal_atr", "confirm_close_location",
    "target_atr", "stop_atr", "time_to_barrier",
]


def load_model(path=None):
    """Load the trained CatBoost model into memory (singleton)."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    path = path or _MODEL_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"Retest model not found: {path}")
    try:
        from catboost import CatBoostClassifier
        _MODEL = CatBoostClassifier()
        _MODEL.load_model(path)
        logger.info(f"Loaded retest model from {path} ({_MODEL.tree_count_} trees)")
    except ImportError:
        logger.warning("catboost not installed — model scoring disabled")
        raise
    return _MODEL


def get_model():
    """Get the loaded model, or None if not loaded."""
    return _MODEL


def get_model_version():
    """Return the model version string from metadata, or 'unknown'."""
    try:
        meta_path = os.path.join(os.path.dirname(_MODEL_PATH), "metadata.json")
        if os.path.exists(meta_path):
            import json
            with open(meta_path) as f:
                meta = json.load(f)
            return meta.get("model_version", "unknown")
    except Exception:
        pass
    return "unknown"


def check_model_drift():
    """Check if model has drifted from training benchmarks.

    Returns dict with model_version, loaded, drift_detected, details.
    """
    result = {
        "model_version": get_model_version(),
        "config_version": cfg.MODEL_VERSION,
        "loaded": _MODEL is not None,
        "drift_detected": False,
        "details": {},
    }
    if _MODEL is None:
        result["details"]["status"] = "no_model_loaded"
        return result
    try:
        meta_path = os.path.join(os.path.dirname(_MODEL_PATH), "metadata.json")
        if os.path.exists(meta_path):
            import json
            with open(meta_path) as f:
                meta = json.load(f)
            result["details"]["training_auc"] = meta.get("test_results", {}).get("auc")
            result["details"]["training_ap"] = meta.get("test_results", {}).get("average_precision")
            result["details"]["n_events"] = meta.get("total_events")
            # Check version match
            if meta.get("model_version") != cfg.MODEL_VERSION:
                result["drift_detected"] = True
                result["details"]["version_mismatch"] = True
    except Exception as e:
        result["details"]["error"] = str(e)
    return result


def populate_historical_scores(market, conn, only_symbols=None, progress_callback=None):
    """Bulk-populate historical_screener.old_swing_retest_score.

    This is a maintenance operation — calls compute_retest_score_for_symbol
    per symbol and writes the time series to historical_screener.
    """
    import pandas as pd
    c = conn.cursor()

    if only_symbols:
        placeholders = ",".join(["?"] * len(only_symbols))
        c.execute(f"SELECT symbol FROM stats WHERE symbol IN ({placeholders})", only_symbols)
    else:
        c.execute("SELECT symbol FROM stats ORDER BY symbol")
    symbols = [row[0] for row in c.fetchall()]

    total = len(symbols)
    written = 0
    skipped = 0

    logger.info(f"Populating historical retest scores for {total} symbols in {market}")

    for i, sym in enumerate(symbols):
        # Get bars for this symbol
        c.execute(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE timeframe='1Day' AND symbol=? ORDER BY date",
            (sym,)
        )
        rows = c.fetchall()
        if len(rows) < 60:
            skipped += 1
            continue

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["market"] = market
        df["symbol"] = sym

        try:
            series = compute_retest_score_for_symbol(df)
        except Exception:
            skipped += 1
            continue

        if len(series) != len(df):
            skipped += 1
            continue

        # Find the symbol's latest historical date
        c.execute("SELECT MAX(date) FROM historical_screener WHERE symbol=?", (sym,))
        latest_hist = c.fetchone()[0]

        # Build bulk update list: only dates after latest_hist
        updates = []
        for j, (date_val, score) in enumerate(zip(df["date"], series)):
            if latest_hist and str(date_val)[:10] <= str(latest_hist):
                continue
            if pd.isna(score):
                continue
            updates.append((round(float(score), 2), str(date_val)[:10], sym))

        if updates:
            c.executemany(
                "UPDATE historical_screener SET old_swing_retest_score=? WHERE date=? AND symbol=?",
                updates
            )
            written += len(updates)

        if progress_callback and (i + 1) % 50 == 0:
            progress_callback(i + 1, total, f"historical_retest: {i+1}/{total} symbols, {written} rows written")

    conn.commit()
    logger.info(f"Historical retest score population complete: {written} rows written, {skipped} skipped")
    return {"written": written, "skipped": skipped, "symbols_processed": total}


def _event_to_feature_array(cycle, zones):
    """Extract 29-feature numpy array from an EventCycle for model prediction."""
    zone_info = None
    for z in zones:
        if z.id == cycle.zone_id:
            zone_info = {
                "prominence": z.prominence_atr,
                "width": z.width_atr,
                "reactions": z.reactions,
                "false_breakouts": z.false_breakouts,
            }
            break

    def nan_to(val, default):
        return float(val) if not np.isnan(val) else default

    return np.array([[
        nan_to(cycle.breakout_body_atr, 0.0),
        nan_to(cycle.breakout_close_location, 0.5),
        nan_to(cycle.breakout_gap_atr, 0.0),
        nan_to(cycle.breakout_volume_ratio, 1.0),
        float(cycle.breakout_consecutive_closes),
        nan_to(cycle.breakout_prior_close_rel, 0.0),
        float(cycle.breakout_retreat_within_3),
        float(cycle.age_at_breakout),
        nan_to(cycle.retest_low_atr, 0.0),
        nan_to(cycle.retest_depth_atr, 0.0),
        float(cycle.retest_touch_candles),
        float(cycle.retest_closes_below_level),
        nan_to(cycle.retest_volume_ratio, 1.0),
        float(zone_info["prominence"]) if zone_info else 1.5,
        float(zone_info["width"]) if zone_info else 0.5,
        float(zone_info["reactions"]) if zone_info else 0,
        float(zone_info["false_breakouts"]) if zone_info else 0,
        float(cycle.age_band),
        float(cycle.trend_higher_highs),
        nan_to(cycle.context_pivot_low_dist_atr, 0.0),
        nan_to(cycle.sma20_slope_atr, 0.0),
        float(cycle.sma20_above_sma60),
        float(np.log1p(cycle.median_traded_value)) if not np.isnan(cycle.median_traded_value) else 0.0,
        float(cycle.entry),
        float(cycle.signal_atr),
        nan_to(cycle.confirm_close_location, 0.5),
        float(cfg.BARRIER_UP_ATR),
        float(abs(cfg.BARRIER_DOWN_ATR)),
        float(cfg.TIME_BARRIER),
    ]]).astype(np.float32)


def make_score_fn(model):
    """Create a score_fn(cycle, zones) -> float (0-100) for the engine."""
    def score_fn(cycle, zones):
        feat = _event_to_feature_array(cycle, zones)
        prob = model.predict_proba(feat)[0, 1]
        return float(prob * 100)
    return score_fn


def compute_retest_score_for_symbol(grp, model=None):
    """Compute OLD_SWING_RETEST_SCORE for a single symbol's full history.

    Returns a pandas Series indexed by the input date index, with NaN where
    no active (unresolved) signal is present. If a model is loaded, scores
    are model-derived (0-100). If no model, returns NaN (structure-only).
    """
    import pandas as pd

    if len(grp) < 60:
        return pd.Series(np.nan, index=grp.index)

    grp = grp.sort_values("date").reset_index(drop=True)
    dates = grp["date"].astype(str).tolist()
    o = grp["open"].astype(float).values
    h = grp["high"].astype(float).values
    l = grp["low"].astype(float).values
    c = grp["close"].astype(float).values
    v = grp["volume"].astype(float).values

    atr = wilders_atr(h, l, c)

    market = grp.get("market", "US")[0] if "market" in grp.columns else "US"
    symbol = grp.get("symbol", "UNKNOWN")[0] if "symbol" in grp.columns else "UNKNOWN"

    # Determine score_fn
    loaded_model = model or _MODEL
    score_fn = None
    if loaded_model is not None:
        try:
            score_fn = make_score_fn(loaded_model)
        except Exception as e:
            logger.warning(f"Failed to create score_fn: {e}")

    try:
        result = fold_symbol(h, l, c, o, v, dates, market, symbol, score_fn=score_fn)
    except Exception:
        return pd.Series(np.nan, index=grp.index)

    n = len(c)
    scores = np.full(n, np.nan, dtype=np.float64)

    for i in range(n):
        s = result.current_scores[i]
        if s is not None and not np.isnan(s):
            scores[i] = s

    return pd.Series(scores, index=grp.index)
