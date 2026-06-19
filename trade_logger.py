"""
Trade logger. The single source of truth for your ML dataset.

Workflow:
  1. When a setup forms, score it with the tier model, build a TradeRecord
     with tier, risk_pct and size filled, then call log_signal().
  2. When the trade closes, call close_trade() with the exit details.
  3. Call to_dataframe() any time to load every trade for training or review.

Storage is a flat CSV so it stays easy to inspect and to version in git.
For a few thousand trades this is more than enough.
"""

import os
import uuid
import pandas as pd

from feature_schema import TradeRecord, Outcome, ExitReason, fieldnames


class TradeLogger:
    def __init__(self, path: str = "trades.csv"):
        self.path = path
        if not os.path.exists(path):
            pd.DataFrame(columns=fieldnames()).to_csv(path, index=False)

    def _load(self) -> pd.DataFrame:
        return pd.read_csv(self.path)

    def _save(self, df: pd.DataFrame) -> None:
        df.to_csv(self.path, index=False)

    def log_signal(self, record: TradeRecord) -> str:
        if not record.trade_id:
            record.trade_id = uuid.uuid4().hex[:12]
        df = self._load()
        df = pd.concat([df, pd.DataFrame([record.to_row()])], ignore_index=True)
        self._save(df)
        return record.trade_id

    def close_trade(self, trade_id: str, exit_time: str, exit_price: float,
                    exit_reason: ExitReason, outcome: Outcome,
                    realized_r: float, pnl: float, bars_held: int,
                    mae_atr: float = None, mfe_atr: float = None) -> None:
        df = self._load()
        mask = df["trade_id"] == trade_id
        if not mask.any():
            raise KeyError(f"trade_id {trade_id} not found")
        updates = {
            "exit_time": exit_time,
            "exit_price": exit_price,
            "exit_reason": exit_reason.value,
            "outcome": outcome.value,
            "realized_r": realized_r,
            "pnl": pnl,
            "bars_held": bars_held,
            "mae_atr": mae_atr,
            "mfe_atr": mfe_atr,
        }
        for col, val in updates.items():
            df[col] = df[col].astype(object)   # avoid float dtype coercion
            df.loc[mask, col] = val
        self._save(df)

    def to_dataframe(self) -> pd.DataFrame:
        return self._load()

    def open_trades(self) -> pd.DataFrame:
        df = self._load()
        return df[df["outcome"] == Outcome.OPEN.value]
