from pathlib import Path
import json

import numpy as np
import pandas as pd

from app.services.forecast_adapters import MovingAverageQuantileAdapter


def test_model_metrics_are_real_and_finite():
    root = Path(__file__).resolve().parents[1]
    model = json.loads((root / "models" / "moving_average_v1.json").read_text(encoding="utf-8"))
    assert model["name"] == "Moving average 7"
    assert model["training"]["observed_days"] == 121
    for value in model["evaluation"].values():
        assert np.isfinite(value)
    assert model["evaluation"]["WAPE"] > 0.5


def test_adapter_quantile_order():
    root = Path(__file__).resolve().parents[1]
    daily = pd.read_csv(root / "data" / "processed" / "daily_sales.csv", parse_dates=["date"])
    series = daily.set_index("date")["net_sales"].reindex(pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")).interpolate().rename("sales").rename_axis("date").reset_index()
    output = MovingAverageQuantileAdapter(root / "models" / "moving_average_v1.json").forecast(series, 30)
    assert len(output.median) == 30
    assert np.all(output.lower <= output.median)
    assert np.all(output.median <= output.upper)
    assert np.all(output.median >= 0)
