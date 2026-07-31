from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import case, func, select

from app.models import Alert, DeclineFactor, Forecast, ModelRun, Recommendation, Sale, SystemSetting
from .forecast_adapters import ForecastAdapter, ForecastOutput

FACTOR_LABELS = {
    "unit_price": ("السعر", "Price"),
    "discount_percent": ("نسبة الخصم", "Discount"),
    "is_promotion": ("العرض الترويجي", "Promotion"),
    "quantity": ("الكمية", "Quantity"),
    "returns": ("المرتجعات", "Returns"),
    "channel_mix": ("مزيج قنوات البيع", "Sales-channel mix"),
}

RECOMMENDATIONS = {
    "unit_price": (
        "راجع أثر السعر على الكمية والقيمة قبل تنفيذ أي تغيير واسع.",
        "Review price impact on volume and value before any broad change.",
    ),
    "discount_percent": (
        "قارن الخصومات بالزيادة الفعلية في الكمية وتجنب الخصم غير المنتج.",
        "Compare discounts with actual volume lift and avoid unproductive discounting.",
    ),
    "is_promotion": (
        "اختبر حملة محدودة مع خط أساس واضح قبل التوسع.",
        "Test a limited campaign against a clear baseline before scaling.",
    ),
    "quantity": (
        "راجع المنتجات والفئات التي تراجعت كمياتها خلال آخر أسبوعين.",
        "Review products and categories whose quantities fell during the last two weeks.",
    ),
    "returns": (
        "افحص أسباب الإشعارات الدائنة والمنتجات الأعلى مرتجعات.",
        "Inspect credit-note causes and products with the highest returns.",
    ),
    "channel_mix": (
        "قارن أداء قنوات البيع الأربع وحدد القناة المسؤولة عن التغير.",
        "Compare the four sales channels and isolate the channel driving the change.",
    ),
}


@dataclass
class ForecastFilters:
    branch_id: int | None = None
    product_id: int | None = None
    category_id: int | None = None
    region_id: int | None = None
    channel: str | None = None

    def as_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if value not in (None, "")}


class InsufficientDataError(ValueError):
    pass


def _query_sales(db, filters: ForecastFilters) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    stmt = select(
        Sale.sale_date,
        func.sum(Sale.net_sales).label("sales"),
        func.avg(Sale.unit_price).label("unit_price"),
        func.avg(Sale.discount_percent).label("discount_percent"),
        func.avg(func.cast(Sale.is_promotion, type_=Sale.discount_percent.type)).label("is_promotion"),
        func.sum(Sale.quantity).label("quantity"),
        func.sum(case((Sale.transaction_type != "INV", func.abs(Sale.net_sales)), else_=0)).label("returns"),
    )
    if filters.branch_id:
        stmt = stmt.where(Sale.branch_id == filters.branch_id)
    if filters.product_id:
        stmt = stmt.where(Sale.product_id == filters.product_id)
    if filters.channel:
        stmt = stmt.where(Sale.channel == filters.channel)
    if filters.category_id:
        from app.models import Product
        stmt = stmt.join(Product, Product.id == Sale.product_id).where(Product.category_id == filters.category_id)
    if filters.region_id:
        from app.models import Branch
        stmt = stmt.join(Branch, Branch.id == Sale.branch_id).where(Branch.region_id == filters.region_id)
    stmt = stmt.group_by(Sale.sale_date).order_by(Sale.sale_date)
    rows = db.execute(stmt).all()
    frame = pd.DataFrame(rows, columns=[
        "date", "sales", "unit_price", "discount_percent", "is_promotion", "quantity", "returns"
    ])
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    for column in frame.columns[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    full_dates = pd.date_range(frame["date"].min(), frame["date"].max(), freq="D")
    frame = frame.set_index("date").reindex(full_dates).rename_axis("date").reset_index()
    frame["observed_day"] = frame["sales"].notna().astype(int)
    frame["sales"] = frame["sales"].interpolate(method="linear", limit_direction="both")
    for column in ["unit_price", "discount_percent", "is_promotion", "quantity", "returns"]:
        frame[column] = frame[column].interpolate(limit_direction="both").fillna(0.0)
    return frame


def _baseline(history: pd.DataFrame, horizon: int) -> np.ndarray:
    sales = history["sales"].to_numpy(dtype=float)
    return np.asarray([max(0.0, float(np.mean(sales[-7:]))) for _ in range(horizon)], dtype=float)


def _normal_cdf(values: np.ndarray) -> np.ndarray:
    return np.asarray([0.5 * (1.0 + math.erf(float(value) / math.sqrt(2.0))) for value in values])


def _probability_below_threshold(output: ForecastOutput, baseline: np.ndarray, decline_threshold: float) -> np.ndarray:
    target = baseline * (1.0 - decline_threshold)
    sigma = np.maximum((output.upper - output.lower) / (2.0 * 1.2815515655446004), 1e-6)
    return np.clip(_normal_cdf((target - output.median) / sigma), 0.0, 1.0)


def _severity(probability: float, decline_percent: float) -> str:
    if probability >= 0.85 and decline_percent >= 0.20:
        return "critical"
    if probability >= 0.70 and decline_percent >= 0.12:
        return "high"
    if probability >= 0.50:
        return "medium"
    return "low"


def _explain_factors(history: pd.DataFrame) -> list[dict]:
    if len(history) < 60:
        return []
    data = history.copy()
    data["sales_change"] = data["sales"].pct_change().replace([np.inf, -np.inf], np.nan)
    features = ["unit_price", "discount_percent", "is_promotion", "quantity", "returns"]
    factors: list[dict] = []
    recent = data.tail(14)
    previous = data.iloc[-28:-14]
    for feature in features:
        series = data[[feature, "sales_change"]].dropna()
        correlation = float(series[feature].corr(series["sales_change"])) if len(series) >= 20 else 0.0
        if not np.isfinite(correlation):
            correlation = 0.0
        recent_mean = float(recent[feature].mean())
        previous_mean = float(previous[feature].mean()) if not previous.empty else recent_mean
        scale = max(abs(previous_mean), 1.0)
        relative_shift = (recent_mean - previous_mean) / scale
        impact = correlation * relative_shift
        ar, en = FACTOR_LABELS[feature]
        factors.append({
            "code": feature,
            "name_ar": ar,
            "name_en": en,
            "impact": impact,
            "direction": "positive" if impact >= 0 else "negative",
            "importance": abs(correlation),
        })
    factors.sort(key=lambda item: abs(item["impact"]), reverse=True)
    return factors[:4]


def run_forecast(db, adapter: ForecastAdapter, horizon: int, filters: ForecastFilters,
                 decline_threshold: float, min_history_days: int, user_id: int | None = None) -> ModelRun:
    if horizon not in {7, 30, 90}:
        raise ValueError("Horizon must be 7, 30, or 90 days")
    history = _query_sales(db, filters)
    if history.empty or len(history) < min_history_days:
        raise InsufficientDataError(f"At least {min_history_days} days are required; found {len(history)}")
    if horizon == 90 and len(history) < 365:
        raise InsufficientDataError(
            "لا تتوفر بيانات تاريخية كافية لإنتاج توقع موثوق لمدة 90 يومًا / "
            "At least 365 days are required for a reliable 90-day forecast"
        )
    run = ModelRun(
        model_name=getattr(adapter, "name", "Unknown"),
        model_version=getattr(adapter, "version", "unknown"),
        status="running",
        horizon_days=horizon,
        filters_json=filters.as_dict(),
        data_start=history["date"].min().date(),
        data_end=history["date"].max().date(),
        sample_size=len(history),
        created_by_id=user_id,
    )
    db.add(run)
    db.flush()
    try:
        output = adapter.forecast(history, horizon, future_covariates=None)
        baseline = _baseline(history, horizon)
        probabilities = _probability_below_threshold(output, baseline, decline_threshold)
        factors = _explain_factors(history)
        decline_percentages = np.maximum(0.0, (baseline - output.median) / np.maximum(baseline, 1e-6))
        stored_forecasts: list[Forecast] = []
        for index in range(horizon):
            forecast = Forecast(
                model_run=run,
                forecast_date=pd.Timestamp(output.dates[index]).date(),
                scope_type="company" if not filters.as_dict() else next(iter(filters.as_dict().keys())).replace("_id", ""),
                scope_id=next((int(value) for key, value in filters.as_dict().items() if key.endswith("_id")), None),
                predicted_sales=Decimal(str(round(max(0.0, float(output.median[index])), 2))),
                lower_bound=Decimal(str(round(max(0.0, float(output.lower[index])), 2))),
                upper_bound=Decimal(str(round(max(0.0, float(output.upper[index])), 2))),
                baseline_sales=Decimal(str(round(max(0.0, float(baseline[index])), 2))),
                decline_probability=float(probabilities[index]),
                decline_percent=float(decline_percentages[index]),
            )
            db.add(forecast)
            stored_forecasts.append(forecast)
        db.flush()
        peak_index = int(np.argmax(probabilities))
        peak = stored_forecasts[peak_index]
        if peak.decline_probability >= 0.50:
            severity = _severity(peak.decline_probability, peak.decline_percent)
            alert = Alert(
                forecast_id=peak.id,
                severity=severity,
                title_ar="احتمال انخفاض في المبيعات",
                title_en="Possible sales decline",
                message_ar=f"احتمال الانخفاض المحسوب {peak.decline_probability:.0%} في {peak.forecast_date}.",
                message_en=f"Calculated decline probability is {peak.decline_probability:.0%} for {peak.forecast_date}.",
            )
            db.add(alert)
            db.flush()
            for rank, factor in enumerate(factors, start=1):
                db.add(DeclineFactor(
                    forecast_id=peak.id,
                    factor_code=factor["code"],
                    factor_name_ar=factor["name_ar"],
                    factor_name_en=factor["name_en"],
                    impact_value=float(factor["impact"]),
                    direction=factor["direction"],
                    method="correlation-and-recent-shift",
                ))
                recommendation = RECOMMENDATIONS.get(factor["code"])
                if recommendation:
                    db.add(Recommendation(
                        alert_id=alert.id,
                        factor_code=factor["code"],
                        text_ar=recommendation[0],
                        text_en=recommendation[1],
                        rationale_ar="مبني على ارتباط تاريخي وتغير آخر 14 يومًا، وليس إثباتًا سببيًا.",
                        rationale_en="Based on historical association and the latest 14-day shift; it is not causal proof.",
                        priority=rank,
                    ))
        run.model_sha256 = output.model_sha256
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.metrics_json = {"source": "reports/model_metrics.json", "observed_days": int(history["observed_day"].sum())}
        return run
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)
        run.completed_at = datetime.now(timezone.utc)
        raise
