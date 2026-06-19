# Trendline trade logger

Foundation for the tier model. It captures every setup with full context at
signal time, then the outcome at close. That logged table is your ML dataset.

## Files
- `feature_schema.py` defines `TradeRecord` and the feature list.
- `sizing.py` maps model probability to tier and tier to risk and size.
- `trade_logger.py` persists trades to CSV and loads them for training.
- `example_usage.py` runs one signal through to close. Run it to smoke test.

## The one rule that matters
Fields are split into two groups:
- SIGNAL TIME features: known when the setup forms. Model inputs only.
- OUTCOME fields: known only after close. Labels only.

`SIGNAL_TIME_FEATURES` lists exactly what the model may see. Train only on
those. If you ever feed an outcome field as an input, your backtest is lying
to you. This split is what keeps the future out of the model.

## Risk per tier (your scheme)
- C = 0.5%
- B = 1.5%
- A = 2.5% up to 4%, scaling with confidence inside the A band

Probability thresholds in `sizing.py` are placeholders. Tune them on out of
sample results, never on data the model trained on.

## Run
```
python3 example_usage.py
```

## Note on the model
The A/B/C decision is a classification on the signal time features. Try a
gradient boosted tree (LightGBM) as the baseline before an LSTM. On tabular
features it usually wins and needs far less data. Reserve the LSTM for the
case where you feed it the raw price sequence into the signal.
