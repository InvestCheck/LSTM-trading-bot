"""Minimal end to end example: log a signal, then close it."""

from datetime import datetime, timezone

from feature_schema import (
    TradeRecord, Direction, SetupType, Session, Regime, Outcome, ExitReason,
)
from sizing import prob_to_tier, tier_to_risk_pct, position_size
from trade_logger import TradeLogger


logger = TradeLogger("trades.csv")

# --- a setup forms; your tier model returns a probability ---
model_prob = 0.71
tier = prob_to_tier(model_prob)
risk_pct = tier_to_risk_pct(tier, model_prob)

equity = 25000.0
entry, stop, target = 1.0850, 1.0820, 1.0920
size = position_size(equity, risk_pct, entry, stop, value_per_point=100000)

record = TradeRecord(
    trade_id="",
    signal_time=datetime.now(timezone.utc).isoformat(),
    instrument="EURUSD",
    timeframe="1h",
    direction=Direction.LONG,
    setup_type=SetupType.BOUNCE,
    line_slope=0.0004,
    line_touches=3,
    line_age_bars=48,
    line_r_squared=0.94,
    dist_to_line_atr=0.3,
    atr=0.0025,
    atr_percentile=0.4,
    realized_vol=0.006,
    htf_trend=Direction.LONG,
    ema_alignment=1.0,
    adx=27.0,
    volume=1500,
    volume_vs_avg=1.2,
    hour=13,
    day_of_week=2,
    session=Session.LONDON,
    regime=Regime.TRENDING,
    in_news_window=False,
    entry_price=entry,
    stop_price=stop,
    target_price=target,
    planned_r=(target - entry) / (entry - stop),
    model_prob=model_prob,
    tier=tier,
    risk_pct=risk_pct,
    position_size=size,
    account_equity=equity,
)

trade_id = logger.log_signal(record)
print(f"logged {trade_id}: tier {tier.value}, risk {risk_pct:.2%}, size {size:.0f} units")

# --- later, the trade hits target ---
logger.close_trade(
    trade_id=trade_id,
    exit_time=datetime.now(timezone.utc).isoformat(),
    exit_price=target,
    exit_reason=ExitReason.TARGET,
    outcome=Outcome.WIN,
    realized_r=record.planned_r,
    pnl=risk_pct * equity * record.planned_r,
    bars_held=22,
    mae_atr=0.4,
    mfe_atr=2.3,
)

print(logger.to_dataframe().tail(1).T)
