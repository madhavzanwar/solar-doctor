# Forecast artifacts

Trained model files (`*.pkl`) and online-adapter checkpoints are NOT committed. Train with
`python -m ml.forecast.training.train --data-path <csv/parquet>`; the registry loads `lgbm_latest.pkl` /
`prob_latest.pkl` from `models/` here (or `$SOLARDOCTOR_FORECAST_ARTIFACTS`). Without an artifact the
service serves a clearly flagged physics-only baseline (`model_name = "physics_baseline"`).
`--dry-run` trains on SYNTHETIC data only; never present such a model as real.
