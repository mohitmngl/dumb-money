"""Single source of truth for the OLD_SWING_RETEST_SCORE engine.

Every threshold, window, and freshness table used by the causal event engine
lives here and nowhere else (RETEST_AUDIT.md section A / spec section B,E,F,G,O).
All values are the canonical spec values; the engine imports from this module.
"""
from enum import Enum

# ------------------------------------------------------------------ swing / zone
SWING_LOOKBACK = 5          # bars on each side of a swing pivot
SWING_CONFIRMATION = 5      # pivot is known at p + SWING_CONFIRMATION (causal)
MIN_PROMINENCE_ATR = 1.5    # min prominence (ATR units) for a pivot to found a zone
ZONE_CLUSTER_ATR = 0.4      # max distance (ATR) between a new pivot and an existing zone to join it

# ------------------------------------------------------------------- level age
MIN_LEVEL_AGE_AT_BREAKOUT = 20          # sessions between zone first pivot and breakout
AGE_BANDS = ((20, 39), (40, 79), (80, 159), (160, 10**9))

# --------------------------------------------------------------------- breakout
BREAKOUT_LEVEL_TOUCH_ATR = 0.25         # close >= level + 0.25 ATR to register a breakout
BREAKOUT_BODY_MIN_ATR = 0.05            # breakout candle body (ATR) must be at least this
BREAKOUT_CLOSE_LOCATION_MIN = 0.60      # (close-low)/(high-low) must be at least this

# ---------------------------------------------------------------------- retest
RETEST_DELAY_MIN = 3        # candles after breakout before a touch counts
RETEST_DELAY_MAX = 80       # candles after breakout after which the cycle expires
RETEST_BOUND_LO_ATR = -0.50 # retest band: level - 0.50 ATR
RETEST_BOUND_HI_ATR = 0.40  # retest band: level + 0.40 ATR
CONFIRM_CLOSE_LEVEL_ATR = -0.10         # confirmation close >= level - 0.10 ATR
CONFIRM_WINDOW = 3                      # candles after the touch to confirm
INVALIDATE_CLOSE_LEVEL_ATR = -0.60      # close < level - 0.60 ATR invalidates the setup

# --------------------------------------------------------------------- outcome
BARRIER_UP_ATR = 2.00       # target: close >= entry + 2.00 * SIGNAL_ATR
BARRIER_DOWN_ATR = -0.75    # stop: low <= entry - 0.75 * SIGNAL_ATR
TIME_BARRIER = 20           # candles after confirmation for resolution
ATR_PERIOD = 14
MFE_MAE_WINDOWS = (5, 10, 20)
DAYS_1ATR = 1.0             # days-to-first-1-ATR excursion barrier

# ------------------------------------------------------------------- freshness
# distance table (spec O): abs((close - level)/SIGNAL_ATR) <= boundary -> freshness
FRESHNESS_DISTANCE = ((0.5, 1.0), (1.0, 0.9), (1.5, 0.7), (2.0, 0.4))
# time table (spec O): candles since confirmation <= boundary -> freshness
FRESHNESS_TIME = ((5, 1.0), (10, 0.9), (15, 0.7), (20, 0.5))

# ----------------------------------------------------------------------- states
class EventStage(str, Enum):
    BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
    WAITING_FOR_RETEST = "WAITING_FOR_RETEST"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    TARGET_REACHED = "TARGET_REACHED"
    STOPPED_OUT = "STOPPED_OUT"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    FAILED = "FAILED"  # touched but never confirmed

class OutcomeClass(str, Enum):
    WIN = "WIN"
    DEEP_DRAWDOWN = "DEEP_DRAWDOWN"
    TIMEOUT = "TIMEOUT"

# ----------------------------------------------------------------- model control
MODEL_VERSION = "v1_20260801"            # increment when model is retrained
MODEL_FEATURES = 29                       # number of input features
MODEL_PATH = "models/retest_v1/model.cbm" # relative to project root
MODEL_METADATA_PATH = "models/retest_v1/metadata.json"
MODEL_THRESHOLD_DEFAULT = 0.30            # default prediction threshold for WIN
MODEL_AUC_TRAINING = 0.694                # documented training AUC for drift detection

# ------------------------------------------------------------------ versioning
RETEST_ENGINE_VERSION = "causal-v1"
RETEST_FEATURE_VERSION = "f29-v1"
RETEST_SCORE_SEMANTICS_VERSION = "new-entry-current-v1"
