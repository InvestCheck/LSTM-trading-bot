"""
Feature schema for the trendline tier model.

The design rule that keeps you from leaking the future into the model:
fields are split into two groups.

  1. SIGNAL TIME features: known the instant a setup forms. These are the
     only fields the model is ever allowed to see as inputs.
  2. OUTCOME fields: known only after the trade closes. These are labels.
     Never feed them to the model as features.

If you keep that split honest, your backtest cannot accidentally peek ahead.
"""

from dataclasses import dataclass, asdict, fields
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


class SetupType(str, Enum):
    BOUNCE = "bounce"      # price rejects off the line
    BREAK = "break"        # price breaks through the line


class Session(str, Enum):
    ASIA = "asia"
    LONDON = "london"
    NEWYORK = "newyork"
    OFF = "off"


class Regime(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    STRESSED = "stressed"


class Tier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    SKIP = "skip"


class Outcome(str, Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    OPEN = "open"


class ExitReason(str, Enum):
    TARGET = "target"
    STOP = "stop"
    TIME = "time"
    MANUAL = "manual"


@dataclass
class TradeRecord:
    # ---------- IDENTITY ----------
    trade_id: str
    signal_time: str                 # ISO timestamp when the setup formed
    instrument: str
    timeframe: str
    direction: Direction
    setup_type: SetupType

    # ---------- SIGNAL TIME FEATURES (model inputs only) ----------
    line_slope: float                # slope of the fitted trendline
    line_touches: int                # confirmed touches before the signal
    line_age_bars: int               # bars since the line was anchored
    line_r_squared: float            # quality of the line fit, 0..1
    dist_to_line_atr: float          # distance from price to line, in ATR
    atr: float
    atr_percentile: float            # ATR rank vs a trailing window, 0..1
    realized_vol: float
    htf_trend: Direction             # higher timeframe trend direction
    ema_alignment: float             # signed score of the EMA stack
    adx: float
    volume: float
    volume_vs_avg: float             # current volume / trailing average
    hour: int
    day_of_week: int
    session: Session
    regime: Regime
    in_news_window: bool             # inside a scheduled release window

    # ---------- PLAN (set at signal) ----------
    entry_price: float
    stop_price: float
    target_price: float
    planned_r: float                 # reward to risk of the plan

    # ---------- SIZING (set at signal, after the model scores it) ----------
    model_prob: Optional[float] = None    # tier model output, 0..1
    tier: Optional[Tier] = None
    risk_pct: Optional[float] = None      # fraction of equity risked
    position_size: Optional[float] = None
    account_equity: Optional[float] = None

    # ---------- OUTCOME (labels, set only at close) ----------
    outcome: Outcome = Outcome.OPEN
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    realized_r: Optional[float] = None    # reward to risk actually achieved
    pnl: Optional[float] = None
    mae_atr: Optional[float] = None       # max adverse excursion, in ATR
    mfe_atr: Optional[float] = None       # max favorable excursion, in ATR
    bars_held: Optional[int] = None

    def to_row(self) -> dict:
        row = asdict(self)
        for k, v in row.items():
            if isinstance(v, Enum):
                row[k] = v.value
        return row


# The only fields the model may use as inputs.
SIGNAL_TIME_FEATURES = [
    "direction", "setup_type", "line_slope", "line_touches", "line_age_bars",
    "line_r_squared", "dist_to_line_atr", "atr", "atr_percentile",
    "realized_vol", "htf_trend", "ema_alignment", "adx", "volume",
    "volume_vs_avg", "hour", "day_of_week", "session", "regime",
    "in_news_window",
]

# Known only after close. Never use these as model inputs.
LABEL_FIELDS = ["outcome", "realized_r", "pnl", "mae_atr", "mfe_atr", "bars_held"]


def fieldnames() -> list:
    return [f.name for f in fields(TradeRecord)]
