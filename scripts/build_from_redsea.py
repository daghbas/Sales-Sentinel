from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from argon2 import PasswordHasher
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import average_precision_score, mean_absolute_error, mean_squared_error, precision_recall_fscore_support
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Config
from app.database import create_all, init_engine, session_scope
from app.models import Branch, Permission, Role, SystemHealth, SystemSetting, User
from app.services.forecast_adapters import MovingAverageQuantileAdapter
from app.services.forecasting_engine import ForecastFilters, run_forecast
from app.services.import_service import clean_sales_frame, import_sales, read_sales_file

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    denominator = np.abs(y_true).sum()
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "WAPE": float(np.abs(y_true - y_pred).sum() / denominator) if denominator else 0.0,
        "sMAPE": float(np.mean(2 * np.abs(y_true - y_pred) / (np.abs(y_true) + np.abs(y_pred) + 1e-9))),
    }


def build_model(daily: pd.DataFrame) -> dict:
    series = daily.set_index("date")["net_sales"].astype(float)
    full_index = pd.date_range(series.index.min(), series.index.max(), freq="D")
    full = series.reindex(full_index)
    missing_dates = [item.date().isoformat() for item in full[full.isna()].index]
    model_series = full.interpolate(method="linear", limit_direction="both")
    features: list[list[float]] = []
    targets: list[float] = []
    dates: list[pd.Timestamp] = []
    for index in range(28, len(model_series)):
        values = model_series.iloc[:index].to_numpy(dtype=float)
        current_date = model_series.index[index]
        features.append([
            values[-1], values[-7], values[-14], values[-28],
            values[-7:].mean(), values[-14:].mean(), values[-28:].mean(),
            values[-7:].std(), current_date.dayofweek, current_date.month,
        ])
        targets.append(float(model_series.iloc[index]))
        dates.append(current_date)
    X = np.asarray(features, dtype=float)
    y = np.asarray(targets, dtype=float)
    split = max(1, int(len(y) * 0.75))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    predictions: dict[str, np.ndarray] = {
        "Naive lag-1": X_test[:, 0],
        "Seasonal lag-7": X_test[:, 1],
        "Moving average 7": X_test[:, 4],
        "Moving average 28": X_test[:, 6],
    }
    extra_trees = ExtraTreesRegressor(n_estimators=400, min_samples_leaf=2, max_features=0.8, random_state=42, n_jobs=-1)
    extra_trees.fit(X_train, y_train)
    predictions["Extra Trees"] = extra_trees.predict(X_test)
    evaluations = {name: metrics(y_test, prediction) for name, prediction in predictions.items()}
    selected_name = min(evaluations, key=lambda name: evaluations[name]["WAPE"])
    selected_prediction = predictions[selected_name]
    residuals = y_test - selected_prediction
    q10, q90 = np.quantile(residuals, [0.1, 0.9])
    baseline = X_test[:, 4]
    threshold = 0.08
    actual_decline = (y_test < baseline * (1 - threshold)).astype(int)
    score = np.clip((baseline - selected_prediction) / (np.abs(baseline) + 1e-9), 0, 1)
    detected = (score >= threshold).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(actual_decline, detected, average="binary", zero_division=0)
    pr_auc = average_precision_score(actual_decline, score) if len(set(actual_decline)) > 1 else 0.0
    return {
        "name": selected_name,
        "version": "redsea-ma7-v1",
        "window": 7,
        "selected_by": "lowest WAPE on chronological 25% hold-out",
        "residual_quantiles": {"q10": float(q10), "q90": float(q90)},
        "evaluation": evaluations[selected_name],
        "all_candidates": evaluations,
        "decline_detection": {"threshold": threshold, "Precision": float(precision), "Recall": float(recall), "F1": float(f1), "PR-AUC": float(pr_auc)},
        "training": {
            "observed_days": int(daily["observed_day"].sum()),
            "calendar_days": int(len(model_series)),
            "imputed_for_model_only": missing_dates,
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "test_start": dates[split].date().isoformat() if split < len(dates) else None,
            "test_end": dates[-1].date().isoformat() if dates else None,
        },
        "limitations": [
            "The source covers one showroom and four months only.",
            "The model is a pilot and its WAPE is too high for production use.",
            "Inventory and detailed campaign identifiers are unavailable.",
            "Two missing dates are linearly imputed for model continuity only and are not stored as factual sales.",
        ],
    }


def build(source: Path, database_path: Path) -> None:
    for directory in [ROOT / "data" / "processed", ROOT / "models", ROOT / "reports", database_path.parent]:
        directory.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()
    Config.DATABASE_URL = f"sqlite:///{database_path}"
    init_engine(Config.DATABASE_URL)
    create_all()
    with session_scope() as db:
        permission_rows = [
            ("dashboard.view", "عرض اللوحة", "View dashboard"),
            ("sales.import", "استيراد المبيعات", "Import sales"),
            ("reports.view", "عرض التقارير", "View reports"),
            ("reports.download", "تنزيل التقارير", "Download reports"),
            ("users.manage", "إدارة المستخدمين", "Manage users"),
            ("system.monitor", "مراقبة النظام", "Monitor system"),
            ("settings.manage", "إدارة الإعدادات", "Manage settings"),
            ("branches.view_all", "عرض جميع الفروع", "View all branches"),
        ]
        permissions = []
        for code, name_ar, name_en in permission_rows:
            permission = Permission(code=code, name_ar=name_ar, name_en=name_en)
            db.add(permission); permissions.append(permission)
        admin_role = Role(code="admin", name_ar="مسؤول النظام", name_en="System Administrator", permissions=permissions)
        analyst_role = Role(code="analyst", name_ar="محلل المبيعات", name_en="Sales Analyst", permissions=[item for item in permissions if item.code in {"dashboard.view", "sales.import", "reports.view", "reports.download", "branches.view_all"}])
        db.add_all([admin_role, analyst_role]); db.flush()
        db.add_all([
            User(username="admin", email="admin@sales-sentinel.local", full_name_ar="مدير النظام", full_name_en="System Administrator", password_hash=HASHER.hash("Admin@2026!"), role=admin_role, locale="ar"),
            User(username="analyst", email="analyst@sales-sentinel.local", full_name_ar="محلل المبيعات", full_name_en="Sales Analyst", password_hash=HASHER.hash("Analyst@2026!"), role=analyst_role, locale="en"),
        ])
        db.add(SystemSetting(key="decline_threshold", value="0.08", value_type="float", description_ar="حد الانخفاض", description_en="Decline threshold"))
    with session_scope() as db:
        result = import_sales(db, source, user_id=1, is_demo=False)
        if result.job.accepted_rows != 2695:
            raise RuntimeError(f"Expected 2695 cleaned rows, got {result.job.accepted_rows}")
    raw = read_sales_file(source)
    clean, _notes = clean_sales_frame(raw)
    processed = clean.copy()
    processed["date"] = processed["date"].astype(str)
    processed.to_csv(ROOT / "data" / "processed" / "redsea_cleaned.csv", index=False, encoding="utf-8-sig")
    processed["date"] = pd.to_datetime(processed["date"])
    daily = processed.groupby("date", as_index=False).agg(
        net_sales=("net_sales", "sum"), total_amount=("total_amount", "sum"), quantity=("quantity", "sum"),
        transactions=("transaction_number", "nunique"), discount_amount=("discount_amount", "sum"),
        vat_amount=("vat_amount", "sum"), return_amount=("net_sales", lambda values: float(np.abs(values[values < 0]).sum())),
    )
    daily["observed_day"] = 1
    daily.to_csv(ROOT / "data" / "processed" / "daily_sales.csv", index=False, encoding="utf-8-sig")
    model = build_model(daily)
    model_path = ROOT / "models" / "moving_average_v1.json"
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "reports" / "model_metrics.json").write_text(json.dumps({**model["evaluation"], **model["decline_detection"]}, indent=2), encoding="utf-8")
    with session_scope() as db:
        branches = db.scalars(select(Branch)).all()
        users = db.scalars(select(User)).all()
        for user in users:
            user.branches = branches
        adapter = MovingAverageQuantileAdapter(model_path)
        run_forecast(db, adapter, 7, ForecastFilters(), 0.08, 90, user_id=1)
        run_forecast(db, adapter, 30, ForecastFilters(), 0.08, 90, user_id=1)
        db.add(SystemHealth(component="SQLite", status="healthy", details_json={"source": source.name, "source_sha256": file_sha256(source), "rows": 2695}, checked_at=datetime.now(timezone.utc)))
        db.add(SystemHealth(component="Forecast model", status="pilot", details_json={"model": model["name"], "WAPE": model["evaluation"]["WAPE"]}, checked_at=datetime.now(timezone.utc)))
    manifest = {
        "source_file": source.name,
        "source_sha256": file_sha256(source),
        "source_rows": int(len(raw)),
        "exact_duplicates_removed": int(len(raw) - len(clean)),
        "accepted_rows": int(len(clean)),
        "date_start": str(pd.to_datetime(clean["date"]).min().date()),
        "date_end": str(pd.to_datetime(clean["date"]).max().date()),
        "observed_days": int(daily["observed_day"].sum()),
        "calendar_days": int((daily["date"].max() - daily["date"].min()).days + 1),
        "missing_calendar_dates": model["training"]["imputed_for_model_only"],
        "is_synthetic": False,
        "sama_weekly_used_for_training": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (ROOT / "data" / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"database": str(database_path), "manifest": manifest, "model": model}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "raw" / "RedSea_Data_Cleaned.csv")
    parser.add_argument("--database", type=Path, default=ROOT / "instance" / "sales_sentinel.db")
    args = parser.parse_args()
    build(args.source.resolve(), args.database.resolve())


if __name__ == "__main__":
    main()
