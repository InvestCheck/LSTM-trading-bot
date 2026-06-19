"""
Tier assignment and position sizing.

Risk per tier, as a fraction of account equity (your numbers):
  C = 0.5%
  B = 1.5%
  A = 2.5% up to 4.0%, scaling with model confidence inside the A band

The probability thresholds below are placeholders. Tune them on your own
out of sample results before trusting them. Do not fit them on data the
model already trained on.
"""

from feature_schema import Tier

# Probability thresholds. Tune on your validation set.
A_THRESHOLD = 0.65
B_THRESHOLD = 0.55
C_THRESHOLD = 0.45   # below this, skip the trade entirely

C_RISK = 0.005
B_RISK = 0.015
A_RISK_MIN = 0.025
A_RISK_MAX = 0.040


def prob_to_tier(prob: float) -> Tier:
    if prob >= A_THRESHOLD:
        return Tier.A
    if prob >= B_THRESHOLD:
        return Tier.B
    if prob >= C_THRESHOLD:
        return Tier.C
    return Tier.SKIP


def tier_to_risk_pct(tier: Tier, prob: float) -> float:
    """Fraction of equity to risk. A tier scales with confidence."""
    if tier is Tier.C:
        return C_RISK
    if tier is Tier.B:
        return B_RISK
    if tier is Tier.A:
        # 2.5% at the A threshold, climbing to 4% as prob approaches 1.0
        span = (prob - A_THRESHOLD) / max(1.0 - A_THRESHOLD, 1e-9)
        span = min(max(span, 0.0), 1.0)
        return A_RISK_MIN + span * (A_RISK_MAX - A_RISK_MIN)
    return 0.0


def position_size(account_equity: float, risk_pct: float,
                  entry_price: float, stop_price: float,
                  value_per_point: float = 1.0) -> float:
    """
    Units to trade so that hitting the stop costs exactly risk_pct of equity.

    The stop distance carries the volatility adjustment for you, as long as
    you place stops off ATR or structure rather than a fixed pip count.
    value_per_point converts one point of price move into account currency
    (contract size, lot value, and so on). Set it per instrument.
    """
    risk_amount = account_equity * risk_pct
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0.0
    return risk_amount / (stop_distance * value_per_point)
