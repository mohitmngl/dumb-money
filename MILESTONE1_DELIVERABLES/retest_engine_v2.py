"""Corrected deterministic old-swing-retest engine V2.

Implements the full setup:
OLD IMPORTANT SWING-HIGH RESISTANCE
→ VALID BREAKOUT
→ MEANINGFUL DEPARTURE ABOVE RESISTANCE
→ ACCEPTANCE ABOVE RESISTANCE
→ SUBSTANTIAL EXPANSION
→ CAUSAL POST-BREAKOUT PEAK
→ LATER PULLBACK FROM THAT PEAK
→ DOWNWARD RETURN FROM ABOVE
→ RETURN TO THE ORIGINAL BREAKOUT LEVEL
→ OLD RESISTANCE HOLDS AS SUPPORT
→ CONFIRMATION NEAR SUPPORT
→ LOW-RISK NEW ENTRY

Feature flag: ENABLE_RETEST_ENGINE_V2
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
import os
import logging

import numpy as np

import dumbmoney.retest_config as cfg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# V2 State vocabulary (exact names required by spec)
# ---------------------------------------------------------------------------
class V2State:
    NO_BREAKOUT = "NO_BREAKOUT"
    BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
    WAITING_FOR_DEPARTURE = "WAITING_FOR_DEPARTURE"
    DEPARTURE_ESTABLISHED = "DEPARTURE_ESTABLISHED"
    WAITING_FOR_RETURN = "WAITING_FOR_RETURN"
    ACTIVE_RETEST = "ACTIVE_RETEST"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    CONFIRMED_RETEST = "CONFIRMED_RETEST"
    POST_ENTRY_ACTIVE = "POST_ENTRY_ACTIVE"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    RECOVERY_FROM_BELOW = "RECOVERY_FROM_BELOW"
    STRUCTURALLY_INVALIDATED = "STRUCTURALLY_INVALIDATED"
    TARGET_COMPLETED = "TARGET_COMPLETED"
    STOPPED_OUT = "STOPPED_OUT"
    EXPIRED = "EXPIRED"
    ENTRY_TOO_FAR = "ENTRY_TOO_FAR"

TERMINAL_STATES = {
    V2State.FAILED_BREAKOUT,
    V2State.RECOVERY_FROM_BELOW,
    V2State.STRUCTURALLY_INVALIDATED,
    V2State.TARGET_COMPLETED,
    V2State.STOPPED_OUT,
    V2State.EXPIRED,
    V2State.ENTRY_TOO_FAR,
}

# ---------------------------------------------------------------------------
# V2 Configuration constants
# ---------------------------------------------------------------------------
# Breakout
V2_BREAKOUT_LEVEL_TOUCH_ATR = 0.25
V2_BREAKOUT_BODY_MIN_ATR = 0.05
V2_BREAKOUT_CLOSE_LOCATION_MIN = 0.60

# Departure
V2_MIN_BARS_BEFORE_RETEST_ELIGIBLE = 8
V2_MIN_DEPARTURE_DISTANCE_ATR = 1.75
V2_MIN_DEPARTURE_CLOSES = 3
V2_DEPARTURE_CLOSE_THRESHOLD_ATR = 0.50
V2_MAX_BARS_TO_ESTABLISH_DEPARTURE = 60

# Failed breakout before departure
V2_FAILED_BREAKOUT_CLOSE_BELOW_ATR = 0.25
V2_FAILED_BREAKOUT_CONSECUTIVE_BELOW = 2

# Pullback
V2_MIN_PULLBACK_FROM_PEAK_ATR = 1.00

# Return from above
V2_RETURN_ABOVE_MIN_CLOSE_ATR = 0.30
V2_RETURN_ABOVE_MIN_CLOSES_5 = 3
V2_RETURN_ABOVE_MAX_CLOSES_BELOW = 0

# Retest zone (touch)
V2_TOUCH_LOWER_ATR = -0.50
V2_TOUCH_UPPER_ATR = 0.40
V2_MAX_BREAKOUT_TO_TOUCH_BARS = 120

# Confirmation
V2_CONFIRM_CLOSE_ATR = -0.10
V2_CONFIRM_WINDOW = 3
V2_INVALIDATE_CLOSE_ATR = -0.60
V2_MAX_ENTRY_DISTANCE_ATR = 0.75

# Barriers
V2_TARGET_ATR = 2.00
V2_STOP_ATR = -0.75
V2_TIME_BARRIER = 20

# Deduplication
V2_OVERLAP_ATR_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# ATR (reused from V1)
# ---------------------------------------------------------------------------
def wilders_atr(high, low, close, period=cfg.ATR_PERIOD):
    """Wilder ATR(period)."""
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


# ---------------------------------------------------------------------------
# Score normalization helper
# ---------------------------------------------------------------------------
def normalize_current_retest_score(value):
    """Normalize a retest score value.
    
    Returns:
        None if no-signal (NaN/None), float rounded to 2 decimals if numeric,
        raises ValueError for inf or malformed values.
    """
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, float) and (np.isinf(value)):
        raise ValueError(f"Invalid score: {value}")
    try:
        fval = float(value)
        if np.isnan(fval) or np.isinf(fval):
            raise ValueError(f"Invalid score: {value}")
        return round(fval, 2)
    except (TypeError, ValueError):
        raise ValueError(f"Cannot normalize score: {value}")


# ---------------------------------------------------------------------------
# V2 Pivot and Zone dataclasses
# ---------------------------------------------------------------------------
@dataclass
class V2Pivot:
    idx: int
    date: str
    price: float
    kind: str  # 'H' or 'L'
    prominence_atr: Optional[float] = None


@dataclass
class V2FrozenZone:
    """Immutable zone snapshot frozen at breakout."""
    zone_id: int
    zone_version: int
    zone_level_at_breakout: float
    member_pivots: list  # list of V2Pivot
    pivot_confirmation_dates: list  # list of str
    width_sessions: int
    width_atr: float
    prominence_atr: float
    reaction_count: int
    false_breakout_count: int
    first_known_date: str
    level_age_at_breakout: int


@dataclass
class V2Event:
    """One complete retest event with all metadata."""
    event_id: str
    zone_id: int
    zone_version: int
    state: str = V2State.NO_BREAKOUT

    # Breakout
    breakout_idx: int = -1
    breakout_date: str = ""
    breakout_close: float = np.nan
    breakout_level: float = np.nan  # frozen zone level
    breakout_atr: float = np.nan
    breakout_body_atr: float = np.nan
    breakout_close_location: float = np.nan
    breakout_gap_atr: float = np.nan
    breakout_volume_ratio: float = np.nan
    breakout_prior_close_rel: float = np.nan
    age_at_breakout: int = -1
    age_band: int = -1

    # Departure
    departure_established_idx: int = -1
    departure_established_date: str = ""
    departure_high_distance_atr: float = np.nan
    departure_close_distance_atr: float = np.nan
    departure_accepted_close_count: int = 0
    departure_bars_held_above: int = 0
    running_peak_price: float = np.nan
    running_peak_date: str = ""
    running_peak_idx: int = -1

    # Return from above
    return_prior_close_above_count: int = 0
    return_closes_above_5: int = 0
    return_closes_below_count: int = 0
    return_slope: float = np.nan
    return_level_crossings: int = 0

    # Touch / retest
    touch_idx: int = -1
    touch_date: str = ""
    touch_low: float = np.nan
    touch_high: float = np.nan
    touch_atr: float = np.nan
    frozen_peak_price: float = np.nan
    frozen_peak_idx: int = -1
    pullback_from_peak_atr: float = np.nan
    peak_distance_above_level: float = np.nan
    bars_breakout_to_peak: int = 0
    bars_peak_to_touch: int = 0
    retracement_fraction: float = np.nan

    # Confirmation
    confirm_idx: int = -1
    confirm_date: str = ""
    entry: float = np.nan
    signal_atr: float = np.nan
    entry_distance_atr: float = np.nan
    confirm_close_location: float = np.nan

    # Score
    original_score: Optional[float] = None
    new_entry_score: Optional[float] = None
    confirmed_this_bar: bool = False
    model_used: bool = False
    model_version: str = ""

    # Outcome
    resolution_idx: int = -1
    resolution_date: str = ""
    outcome: Optional[str] = None
    reason: str = ""

    # Frozen zone snapshot
    frozen_zone: Optional[V2FrozenZone] = None

    def as_dict(self):
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, float):
                d[k] = None if np.isnan(v) else v
            elif isinstance(v, V2FrozenZone):
                d[k] = {
                    "zone_id": v.zone_id,
                    "zone_version": v.zone_version,
                    "zone_level_at_breakout": v.zone_level_at_breakout,
                    "width_sessions": v.width_sessions,
                    "width_atr": v.width_atr,
                    "prominence_atr": v.prominence_atr,
                    "reaction_count": v.reaction_count,
                    "false_breakout_count": v.false_breakout_count,
                    "first_known_date": v.first_known_date,
                    "level_age_at_breakout": v.level_age_at_breakout,
                }
            else:
                d[k] = v
        return d


# ---------------------------------------------------------------------------
# V2 FoldState
# ---------------------------------------------------------------------------
@dataclass
class V2FoldState:
    market: str
    symbol: str
    zones: list = field(default_factory=list)
    swings_high: list = field(default_factory=list)
    swings_low: list = field(default_factory=list)
    events: list = field(default_factory=list)
    next_zone_id: int = 0
    next_event_seq: int = 0
    watermark: int = -1

    def to_dict(self):
        return {
            "market": self.market, "symbol": self.symbol,
            "next_zone_id": self.next_zone_id, "next_event_seq": self.next_event_seq,
            "watermark": self.watermark,
        }


@dataclass
class V2FoldResult:
    market: str
    symbol: str
    dates: list
    current_scores: np.ndarray
    original_scores: np.ndarray
    states: list
    events: list
    watermark: int
    model_used: bool
    model_version: str


# ---------------------------------------------------------------------------
# V2 Zone (mutable during fold, frozen at breakout)
# ---------------------------------------------------------------------------
@dataclass
class V2Zone:
    id: int
    symbol: str
    market: str
    members: list = field(default_factory=list)
    cycle_seq: int = 0
    reactions: int = 0
    false_breakouts: int = 0
    exhausted: bool = False
    last_probe_idx: int = -10
    version: int = 0  # increments when members change

    @property
    def first_idx(self):
        return self.members[0].idx if self.members else -1

    @property
    def last_idx(self):
        return self.members[-1].idx if self.members else -1

    @property
    def level(self):
        if not self.members:
            return 0.0
        w = np.array([m.prominence_atr or 1.0 for m in self.members], dtype=np.float64)
        p = np.array([m.price for m in self.members], dtype=np.float64)
        return float(np.average(p, weights=w))

    @property
    def prominence_atr(self):
        if not self.members:
            return 0.0
        return max((m.prominence_atr or 0.0) for m in self.members)

    def age(self, t):
        return t - self.first_idx if self.first_idx >= 0 else 0

    def freeze_at_breakout(self, breakout_idx, breakout_date):
        """Create immutable snapshot of zone at breakout time."""
        return V2FrozenZone(
            zone_id=self.id,
            zone_version=self.version,
            zone_level_at_breakout=self.level,
            member_pivots=list(self.members),
            pivot_confirmation_dates=[m.date for m in self.members],
            width_sessions=self.last_idx - self.first_idx if self.members else 0,
            width_atr=self._width_atr(),
            prominence_atr=self.prominence_atr,
            reaction_count=self.reactions,
            false_breakout_count=self.false_breakouts,
            first_known_date=self.members[0].date if self.members else "",
            level_age_at_breakout=self.age(breakout_idx),
        )

    def _width_atr(self):
        if len(self.members) < 2:
            return 0.0
        lo = min(m.price for m in self.members)
        hi = max(m.price for m in self.members)
        base = self.members[-1].prominence_atr or 1.0
        return (hi - lo) / base if base > 0 else 0.0


# ---------------------------------------------------------------------------
# V2 Engine
# ---------------------------------------------------------------------------
class RetestEngineV2:
    """Corrected deterministic fold for one symbol."""

    def __init__(self, market, symbol, score_fn=None):
        self.market = market
        self.symbol = symbol
        self.score_fn = score_fn
        self.state = V2FoldState(market, symbol)

    def fold(self, dates, open_, high, low, close, volume, initial_state=None, start_idx=0):
        n = len(close)
        empty = V2FoldResult(
            self.market, self.symbol, list(dates),
            np.full(n, np.nan), np.full(n, np.nan),
            [V2State.NO_BREAKOUT] * n, [], n - 1,
            self.score_fn is not None, cfg.MODEL_VERSION
        )
        if n < cfg.SWING_LOOKBACK + cfg.SWING_CONFIRMATION + 2:
            return empty
        if initial_state is not None:
            self.state = initial_state
        elif start_idx == 0:
            self.state = V2FoldState(self.market, self.symbol)

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
        state_strs = [V2State.NO_BREAKOUT] * n

        for t in range(start_idx, n):
            p = t - cfg.SWING_CONFIRMATION
            if p >= cfg.SWING_LOOKBACK and p < n:
                self._confirm_swing_high(high, low, atr, dates, p)
                self._confirm_swing_low(high, low, atr, dates, p)
            best = self._advance_cycles(high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t)
            if best is not None:
                current[t], original[t], state_strs[t] = best
        self.state.watermark = n - 1
        return V2FoldResult(
            self.market, self.symbol, list(dates), current, original, state_strs,
            list(self.state.events), n - 1,
            self.score_fn is not None, cfg.MODEL_VERSION
        )

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
            piv = V2Pivot(p, dates[p], float(high[p]), "H",
                         float(prom_atr) if prom_atr is not None else None)
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
            piv = V2Pivot(p, dates[p], float(low[p]), "L", None)
            self.state.swings_low.append(piv)
            if len(self.state.swings_low) > 80:
                del self.state.swings_low[0]

    def _zone_worthy_pivot(self, piv, atr_now):
        best, best_d = None, None
        for z in self.state.zones:
            if z.exhausted:
                continue
            d = abs(z.level - piv.price)
            if d <= cfg.ZONE_CLUSTER_ATR * atr_now and (best is None or d < best_d):
                best, best_d = z, d
        if best is not None:
            best.members.append(piv)
            best.version += 1
        else:
            z = V2Zone(self.state.next_zone_id, self.symbol, self.market, [piv])
            self.state.next_zone_id += 1
            self.state.zones.append(z)

    # -------------------------------------------------------------- per-bar
    def _advance_cycles(self, high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t):
        a = atr[t]
        best_visible = None
        for z in self.state.zones:
            if z.exhausted:
                continue
            lvl = z.level
            # Check if there's an active event for this zone
            active_event = None
            for ev in self.state.events:
                if ev.zone_id == z.id and ev.state not in TERMINAL_STATES:
                    active_event = ev
                    break

            if active_event is None:
                # Check for new breakout
                if (z.age(t) >= cfg.MIN_LEVEL_AGE_AT_BREAKOUT and
                    close[t] >= lvl + V2_BREAKOUT_LEVEL_TOUCH_ATR * a and
                    (t == 0 or close[t - 1] < lvl) and
                    self._breakout_quality(open_, high, low, close, t, a)):
                    ev = self._start_event(z, high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t)
                    best_visible = _pick_visible_v2(best_visible, (np.nan, np.nan, ev.state))
                else:
                    self._count_reactions(z, high, low, close, atr, t, lvl)
                continue
            else:
                # Advance existing event
                terminal, vis = self._advance_event(active_event, z, high, low, close, volume, atr, sma20, sma60, vol20, dates, t)
                if vis is not None:
                    best_visible = _pick_visible_v2(best_visible, vis)
                if terminal:
                    z.cycle_seq += 1

        return best_visible

    def _count_reactions(self, z, high, low, close, atr, t, lvl):
        a = atr[t]
        if np.isnan(a) or a <= 0:
            return
        lo_band = lvl + V2_TOUCH_LOWER_ATR * a
        hi_band = lvl + V2_CONFIRM_CLOSE_ATR * a
        if lo_band <= close[t] < hi_band and high[t] >= hi_band and t - z.last_probe_idx >= 2:
            z.reactions += 1
            z.last_probe_idx = t

    def _breakout_quality(self, open_, high, low, close, t, a):
        if np.isnan(a) or a <= 0:
            return False
        body = abs(close[t] - open_[t]) / a
        rng = high[t] - low[t]
        loc = (close[t] - low[t]) / rng if rng > 0 else 1.0
        return body >= V2_BREAKOUT_BODY_MIN_ATR and loc >= V2_BREAKOUT_CLOSE_LOCATION_MIN

    def _start_event(self, z, high, low, close, open_, volume, atr, sma20, sma60, vol20, dates, t):
        """Start a new breakout event with frozen zone snapshot."""
        self.state.next_event_seq += 1
        ev = V2Event(
            event_id=f"{self.symbol}:{z.id}:{self.state.next_event_seq}",
            zone_id=z.id,
            zone_version=z.version,
        )
        ev.breakout_idx = t
        ev.breakout_date = dates[t]
        ev.breakout_close = float(close[t])
        ev.breakout_level = float(z.level)
        ev.breakout_atr = float(atr[t])
        ev.breakout_body_atr = abs(close[t] - open_[t]) / atr[t]
        rng = high[t] - low[t]
        ev.breakout_close_location = (close[t] - low[t]) / rng if rng > 0 else 1.0
        ev.breakout_gap_atr = (open_[t] - close[t - 1]) / atr[t] if t > 0 else 0.0
        ev.breakout_volume_ratio = volume[t] / vol20[t] if not np.isnan(vol20[t]) and vol20[t] > 0 else np.nan
        ev.breakout_prior_close_rel = (close[t - 1] - z.level) / atr[t] if t > 0 else 0.0
        ev.age_at_breakout = z.age(t)
        ev.age_band = self._age_band(ev.age_at_breakout)

        # Freeze zone snapshot at breakout (causal - only pivots confirmed <= t)
        ev.frozen_zone = z.freeze_at_breakout(t, dates[t])

        ev.state = V2State.BREAKOUT_CONFIRMED
        self.state.events.append(ev)
        return ev

    def _age_band(self, age):
        for i, (lo, hi) in enumerate(cfg.AGE_BANDS):
            if lo <= age <= hi:
                return i
        return -1

    # ----------------------------------------------------------- advance event
    def _advance_event(self, ev, z, high, low, close, volume, atr, sma20, sma60, vol20, dates, t):
        """Advance one event through its state machine."""
        lvl = ev.breakout_level
        a = atr[t]
        st = ev.state
        if np.isnan(a):
            return False, (np.nan, np.nan, st)

        # --- BREAKOUT_CONFIRMED -> WAITING_FOR_DEPARTURE ---
        if st == V2State.BREAKOUT_CONFIRMED:
            if t == ev.breakout_idx:
                return False, (np.nan, np.nan, st)
            ev.state = V2State.WAITING_FOR_DEPARTURE
            return False, (np.nan, np.nan, ev.state)

        # --- WAITING_FOR_DEPARTURE ---
        if st == V2State.WAITING_FOR_DEPARTURE:
            # Check failed breakout before departure
            if self._check_failed_breakout_before_departure(ev, close, atr, t):
                return self._terminate(ev, z, t, dates[t], V2State.FAILED_BREAKOUT, "failed_breakout_before_departure")

            # Check structural invalidation
            if close[t] < lvl + V2_INVALIDATE_CLOSE_ATR * a:
                return self._terminate(ev, z, t, dates[t], V2State.STRUCTURALLY_INVALIDATED, "invalidated_wait")

            # Check timeout
            delay = t - ev.breakout_idx
            if delay > V2_MAX_BREAKOUT_TO_TOUCH_BARS:
                return self._terminate(ev, z, t, dates[t], V2State.EXPIRED, "no_touch_120")

            # Update running peak
            if high[t] > ev.running_peak_price or np.isnan(ev.running_peak_price):
                ev.running_peak_price = float(high[t])
                ev.running_peak_date = dates[t]
                ev.running_peak_idx = t

            # Check departure criteria
            if delay >= V2_MIN_BARS_BEFORE_RETEST_ELIGIBLE:
                if self._check_departure_established(ev, close, atr, t):
                    ev.state = V2State.DEPARTURE_ESTABLISHED
                    ev.state = V2State.WAITING_FOR_RETURN
                    return False, (np.nan, np.nan, ev.state)

            return False, (np.nan, np.nan, ev.state)

        # --- DEPARTURE_ESTABLISHED / WAITING_FOR_RETURN ---
        if st in (V2State.DEPARTURE_ESTABLISHED, V2State.WAITING_FOR_RETURN):
            # Continue updating running peak
            if high[t] > ev.running_peak_price or np.isnan(ev.running_peak_price):
                ev.running_peak_price = float(high[t])
                ev.running_peak_date = dates[t]
                ev.running_peak_idx = t

            # Check timeout
            delay = t - ev.breakout_idx
            if delay > V2_MAX_BREAKOUT_TO_TOUCH_BARS:
                return self._terminate(ev, z, t, dates[t], V2State.EXPIRED, "no_touch_120")

            # Check for valid touch (retest)
            if self._check_valid_touch(ev, low, atr, t):
                # Freeze peak before touch
                ev.frozen_peak_price = ev.running_peak_price
                ev.frozen_peak_idx = ev.running_peak_idx
                ev.touch_idx = t
                ev.touch_date = dates[t]
                ev.touch_low = float(low[t])
                ev.touch_high = float(high[t])
                ev.touch_atr = a

                # Calculate pullback
                if not np.isnan(ev.frozen_peak_price) and not np.isnan(ev.touch_low):
                    ev.pullback_from_peak_atr = (ev.frozen_peak_price - ev.touch_low) / ev.breakout_atr
                    ev.peak_distance_above_level = (ev.frozen_peak_price - lvl) / ev.breakout_atr
                    ev.bars_breakout_to_peak = ev.frozen_peak_idx - ev.breakout_idx
                    ev.bars_peak_to_touch = t - ev.frozen_peak_idx

                # Check pullback minimum
                if ev.pullback_from_peak_atr < V2_MIN_PULLBACK_FROM_PEAK_ATR:
                    return self._terminate(ev, z, t, dates[t], V2State.STRUCTURALLY_INVALIDATED, "insufficient_pullback")

                # Check return from above
                if not self._check_return_from_above(ev, close, atr, t):
                    return self._terminate(ev, z, t, dates[t], V2State.RECOVERY_FROM_BELOW, "recovery_from_below")

                ev.state = V2State.ACTIVE_RETEST
                return False, (np.nan, np.nan, ev.state)

            # Check for deep breakdown
            if close[t] < lvl + V2_TOUCH_LOWER_ATR * a:
                return self._terminate(ev, z, t, dates[t], V2State.STRUCTURALLY_INVALIDATED, "deep_breakdown")

            return False, (np.nan, np.nan, ev.state)

        # --- ACTIVE_RETEST ---
        if st == V2State.ACTIVE_RETEST:
            # Check for confirmation
            if close[t] >= lvl + V2_CONFIRM_CLOSE_ATR * a:
                self._confirm(ev, z, t, dates[t], a, high, low, close)
                # Check immediate barriers on confirmation candle
                entry = ev.entry
                sa = ev.signal_atr
                hit_stop = low[t] <= entry + V2_STOP_ATR * sa
                hit_target = high[t] >= entry + V2_TARGET_ATR * sa
                if hit_stop and hit_target:
                    return self._terminate(ev, z, t, dates[t], V2State.STOPPED_OUT, "same_candle_stop_first")
                if hit_stop:
                    return self._terminate(ev, z, t, dates[t], V2State.STOPPED_OUT, "barrier_stop")
                if hit_target:
                    return self._terminate(ev, z, t, dates[t], V2State.TARGET_COMPLETED, "barrier_target")
                return False, self._visible(ev, z, close, t)

            # Check confirmation window expiry
            if t > ev.touch_idx + V2_CONFIRM_WINDOW:
                return self._terminate(ev, z, t, dates[t], V2State.EXPIRED, "no_confirmation")

            # Check structural invalidation before confirmation
            if close[t] < lvl + V2_INVALIDATE_CLOSE_ATR * a:
                return self._terminate(ev, z, t, dates[t], V2State.STRUCTURALLY_INVALIDATED, "invalidated_retest")

            return False, (np.nan, np.nan, ev.state)

        # --- WAITING_FOR_CONFIRMATION ---
        if st == V2State.WAITING_FOR_CONFIRMATION:
            if close[t] >= lvl + V2_CONFIRM_CLOSE_ATR * a:
                self._confirm(ev, z, t, dates[t], a, high, low, close)
                entry = ev.entry
                sa = ev.signal_atr
                hit_stop = low[t] <= entry + V2_STOP_ATR * sa
                hit_target = high[t] >= entry + V2_TARGET_ATR * sa
                if hit_stop and hit_target:
                    return self._terminate(ev, z, t, dates[t], V2State.STOPPED_OUT, "same_candle_stop_first")
                if hit_stop:
                    return self._terminate(ev, z, t, dates[t], V2State.STOPPED_OUT, "barrier_stop")
                if hit_target:
                    return self._terminate(ev, z, t, dates[t], V2State.TARGET_COMPLETED, "barrier_target")
                return False, self._visible(ev, z, close, t)

            if t > ev.touch_idx + V2_CONFIRM_WINDOW:
                return self._terminate(ev, z, t, dates[t], V2State.EXPIRED, "no_confirmation")

            if close[t] < lvl + V2_INVALIDATE_CLOSE_ATR * a:
                return self._terminate(ev, z, t, dates[t], V2State.STRUCTURALLY_INVALIDATED, "invalidated_retest")

            return False, (np.nan, np.nan, ev.state)

        # --- POST_ENTRY_ACTIVE ---
        if st == V2State.POST_ENTRY_ACTIVE:
            entry = ev.entry
            sa = ev.signal_atr
            hit_stop = low[t] <= entry + V2_STOP_ATR * sa
            hit_target = high[t] >= entry + V2_TARGET_ATR * sa
            if hit_stop and hit_target:
                return self._terminate(ev, z, t, dates[t], V2State.STOPPED_OUT, "same_candle_stop_first")
            if hit_stop:
                return self._terminate(ev, z, t, dates[t], V2State.STOPPED_OUT, "barrier_stop")
            if hit_target:
                return self._terminate(ev, z, t, dates[t], V2State.TARGET_COMPLETED, "barrier_target")
            if t - ev.confirm_idx >= V2_TIME_BARRIER:
                return self._terminate(ev, z, t, dates[t], V2State.EXPIRED, "timeout_20")
            return False, self._visible(ev, z, close, t)

        return False, None

    def _check_failed_breakout_before_departure(self, ev, close, atr, t):
        """Check if breakout failed before departure was established."""
        lvl = ev.breakout_level
        a = atr[t]
        if np.isnan(a):
            return False
        # Condition 1: one close below level - 0.25 * ATR
        if close[t] < lvl + V2_FAILED_BREAKOUT_CLOSE_BELOW_ATR * a:
            return True
        # Condition 2: two consecutive closes below level
        if t >= 1 and close[t] < lvl and close[t - 1] < lvl:
            return True
        return False

    def _check_departure_established(self, ev, close, atr, t):
        """Check if departure criteria are met."""
        lvl = ev.breakout_level
        a = ev.breakout_atr
        if np.isnan(a) or a <= 0:
            return False

        # Check max post-breakout high
        max_high = ev.running_peak_price if not np.isnan(ev.running_peak_price) else 0
        if max_high < lvl + V2_MIN_DEPARTURE_DISTANCE_ATR * a:
            return False

        # Count closes above threshold
        closes_above = 0
        for i in range(ev.breakout_idx + 1, t + 1):
            if close[i] >= lvl + V2_DEPARTURE_CLOSE_THRESHOLD_ATR * a:
                closes_above += 1
        if closes_above < V2_MIN_DEPARTURE_CLOSES:
            return False

        ev.departure_established_idx = t
        ev.departure_established_date = ""
        ev.departure_high_distance_atr = (max_high - lvl) / a
        ev.departure_accepted_close_count = closes_above
        return True

    def _check_valid_touch(self, ev, low, atr, t):
        """Check if price touched the retest zone."""
        lvl = ev.breakout_level
        a = atr[t]
        if np.isnan(a):
            return False
        lower = lvl + V2_TOUCH_LOWER_ATR * a
        upper = lvl + V2_TOUCH_UPPER_ATR * a
        return lower <= low[t] <= upper

    def _check_return_from_above(self, ev, close, atr, t):
        """Check that price approached from above, not from below."""
        lvl = ev.breakout_level
        a = atr[t]
        if np.isnan(a):
            return False

        # Check immediately previous close
        if t < 1:
            return False
        if close[t - 1] < lvl + V2_RETURN_ABOVE_MIN_CLOSE_ATR * a:
            return False

        # Check 3 of last 5 closes above threshold
        closes_above = 0
        for i in range(max(0, t - 5), t):
            if close[i] >= lvl + V2_RETURN_ABOVE_MIN_CLOSE_ATR * a:
                closes_above += 1
        if closes_above < V2_RETURN_ABOVE_MIN_CLOSES_5:
            return False

        # No close below level - 0.10 * ATR in last 3 candles
        for i in range(max(0, t - 3), t):
            if close[i] < lvl + V2_CONFIRM_CLOSE_ATR * a:
                return False

        return True

    def _confirm(self, ev, z, t, date, atr_now, high, low, close):
        """Confirm the retest and set entry."""
        ev.confirm_idx = t
        ev.confirm_date = date
        ev.entry = float(close[t])
        ev.signal_atr = float(atr_now)
        ev.entry_distance_atr = (close[t] - ev.breakout_level) / ev.signal_atr
        rng = high[t] - low[t]
        ev.confirm_close_location = (close[t] - low[t]) / rng if rng > 0 else 1.0

        # Check entry distance gate
        if ev.entry_distance_atr > V2_MAX_ENTRY_DISTANCE_ATR:
            ev.state = V2State.ENTRY_TOO_FAR
            return

        ev.state = V2State.POST_ENTRY_ACTIVE
        ev.confirmed_this_bar = True

        # Score
        if self.score_fn is not None:
            ev.original_score = self.score_fn(ev, self.state.zones)
            ev.model_used = ev.original_score is not None
        ev.new_entry_score = ev.original_score

    def _terminate(self, ev, z, t, date, state, reason):
        """Terminate an event."""
        ev.state = state
        ev.reason = reason
        ev.resolution_idx = t
        ev.resolution_date = date
        if state in (V2State.FAILED_BREAKOUT, V2State.RECOVERY_FROM_BELOW,
                     V2State.STRUCTURALLY_INVALIDATED, V2State.EXPIRED):
            z.false_breakouts += 1
        if state == V2State.TARGET_COMPLETED:
            z.exhausted = True
        return True, (np.nan, np.nan, state)

    def _visible(self, ev, z, close, t):
        """Get visible score for current bar."""
        if ev.state != V2State.POST_ENTRY_ACTIVE:
            return (np.nan, np.nan, ev.state)
        # Score is only on confirmation bar
        if ev.confirmed_this_bar and t == ev.confirm_idx:
            score = ev.new_entry_score
            orig = ev.original_score if ev.original_score is not None else np.nan
            return (score if score is not None else np.nan, orig, ev.state)
        # After confirmation, current score is NULL
        return (np.nan, np.nan, ev.state)


def _pick_visible_v2(a, b):
    """Deterministic best-visible selection."""
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
    return a


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fold_symbol_v2(high, low, close, open_, volume, dates, market, symbol,
                   score_fn=None, initial_state=None, start_idx=0):
    """Causal fold for one symbol using V2 engine."""
    eng = RetestEngineV2(market, symbol, score_fn)
    if initial_state is not None:
        eng.state = initial_state
        if start_idx == 0:
            start_idx = initial_state.watermark + 1
    return eng.fold(dates, open_, high, low, close, volume, initial_state, start_idx)


def compute_retest_score_current_v2(grp, model=None):
    """Compute current retest score for a symbol using V2 engine."""
    import pandas as pd
    if len(grp) < 60:
        return np.nan

    grp = grp.sort_values("date").reset_index(drop=True)
    dates = grp["date"].astype(str).tolist()
    o = grp["open"].astype(float).values
    h = grp["high"].astype(float).values
    l = grp["low"].astype(float).values
    c = grp["close"].astype(float).values
    v = grp["volume"].astype(float).values

    market = grp.get("market", "US")[0] if "market" in grp.columns else "US"
    symbol = grp.get("symbol", "UNKNOWN")[0] if "symbol" in grp.columns else "UNKNOWN"

    try:
        result = fold_symbol_v2(h, l, c, o, v, dates, market, symbol)
    except Exception:
        return np.nan

    if result is None or len(result.current_scores) == 0:
        return np.nan

    val = result.current_scores[-1]
    return val if not (isinstance(val, float) and np.isnan(val)) else np.nan


def compute_retest_score_for_symbol_v2(grp, model=None):
    """Compute full retest score series using V2 engine."""
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

    market = grp.get("market", "US")[0] if "market" in grp.columns else "US"
    symbol = grp.get("symbol", "UNKNOWN")[0] if "symbol" in grp.columns else "UNKNOWN"

    try:
        result = fold_symbol_v2(h, l, c, o, v, dates, market, symbol)
    except Exception:
        return pd.Series(np.nan, index=grp.index)

    n = len(c)
    scores = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        s = result.current_scores[i]
        if s is not None and not np.isnan(s):
            scores[i] = s

    return pd.Series(scores, index=grp.index)
