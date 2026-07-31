from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ForecastOutput:
    dates: list[pd.Timestamp]
    median: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    model_name: str
    model_version: str
    model_sha256: str | None


class ForecastAdapter(Protocol):
    name: str
    version: str

    def forecast(self, history: pd.DataFrame, horizon: int, future_covariates: pd.DataFrame | None = None) -> ForecastOutput:
        ...


class ModelUnavailableError(RuntimeError):
    pass


class MovingAverageQuantileAdapter:
    """Transparent model selected by chronological hold-out evaluation.

    The bundled JSON contains the actual evaluation metrics and residual
    quantiles calculated from the included Redsea daily dataset. No random
    probabilities or static forecast rows are used.
    """

    name = "Moving Average Quantile Baseline"
    version = "redsea-ma7-v1"

    def __init__(self, model_path: Path):
        self.model_path = model_path

    def forecast(self, history: pd.DataFrame, horizon: int, future_covariates: pd.DataFrame | None = None) -> ForecastOutput:
        if not self.model_path.exists():
            raise ModelUnavailableError(f"Forecast model configuration is missing: {self.model_path}")
        config = json.loads(self.model_path.read_text(encoding="utf-8"))
        window = int(config.get("window", 7))
        values = history["sales"].astype(float).tolist()
        if len(values) < max(28, window):
            raise ModelUnavailableError("At least 28 daily observations are required")
        q10 = float(config["residual_quantiles"]["q10"])
        q90 = float(config["residual_quantiles"]["q90"])
        medians: list[float] = []
        lowers: list[float] = []
        uppers: list[float] = []
        dates: list[pd.Timestamp] = []
        current_date = pd.Timestamp(history["date"].max())
        for _ in range(horizon):
            current_date += pd.Timedelta(days=1)
            prediction = max(0.0, float(np.mean(values[-window:])))
            lower = max(0.0, prediction + q10)
            upper = max(prediction, prediction + q90)
            medians.append(prediction)
            lowers.append(min(lower, prediction))
            uppers.append(upper)
            dates.append(current_date)
            values.append(prediction)
        digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        return ForecastOutput(
            dates=dates,
            median=np.asarray(medians),
            lower=np.asarray(lowers),
            upper=np.asarray(uppers),
            model_name=self.name,
            model_version=self.version,
            model_sha256=digest,
        )
