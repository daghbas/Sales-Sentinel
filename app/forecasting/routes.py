from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import desc, select

from app.database import session_scope
from app.models import Alert, Branch, DeclineFactor, Forecast, ModelRun, Recommendation, Sale
from app.services.audit import write_audit
from app.services.forecast_adapters import ModelUnavailableError, MovingAverageQuantileAdapter
from app.services.forecasting_engine import ForecastFilters, InsufficientDataError, run_forecast
from app.services.security import branch_ids_for_user, current_user, login_required

forecasting_bp = Blueprint("forecasting", __name__, url_prefix="/forecasts")


def _adapter():
    return MovingAverageQuantileAdapter(current_app.config["FORECAST_MODEL_PATH"])


@forecasting_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    user = current_user()
    allowed = branch_ids_for_user(user) if user else set()
    if request.method == "POST":
        horizon = int(request.form.get("horizon", "30"))
        branch_id = request.form.get("branch_id", type=int)
        channel = request.form.get("channel", "").strip() or None
        if branch_id and allowed and branch_id not in allowed:
            return render_template("errors/error.html", code=403, message="Unauthorized branch / فرع غير مصرح"), 403
        filters = ForecastFilters(branch_id=branch_id, channel=channel)
        with session_scope() as db:
            try:
                model_run = run_forecast(
                    db, _adapter(), horizon, filters,
                    current_app.config["DECLINE_THRESHOLD"],
                    current_app.config["MIN_HISTORY_DAYS"],
                    user_id=user.id if user else None,
                )
                write_audit(
                    db, "forecast.run", user_id=user.id if user else None,
                    entity_type="model_run", entity_id=str(model_run.id),
                    details={"horizon": horizon, "filters": filters.as_dict()},
                )
                flash("تم تشغيل التنبؤ بنجاح / Forecast completed successfully", "success")
                run_id = model_run.id
            except (InsufficientDataError, ModelUnavailableError) as exc:
                flash(str(exc), "error")
                return redirect(url_for("forecasting.index"))
        return redirect(url_for("forecasting.detail", run_id=run_id))
    with session_scope() as db:
        branch_stmt = select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)
        if allowed:
            branch_stmt = branch_stmt.where(Branch.id.in_(allowed))
        branches = db.scalars(branch_stmt).all()
        runs = db.scalars(select(ModelRun).order_by(desc(ModelRun.started_at)).limit(20)).all()
        channels = db.scalars(select(Sale.channel).distinct().order_by(Sale.channel)).all()
    return render_template("forecasting/index.html", branches=branches, runs=runs, channels=channels)


@forecasting_bp.get("/<int:run_id>")
@login_required
def detail(run_id: int):
    with session_scope() as db:
        run = db.get(ModelRun, run_id)
        if not run:
            return render_template("errors/error.html", code=404, message="Forecast run not found"), 404
        forecasts = db.scalars(select(Forecast).where(Forecast.model_run_id == run_id).order_by(Forecast.forecast_date)).all()
        alert = db.scalar(
            select(Alert).join(Forecast, Alert.forecast_id == Forecast.id)
            .where(Forecast.model_run_id == run_id).order_by(desc(Alert.created_at))
        )
        factors = []
        recommendations = []
        if alert and alert.forecast_id:
            factors = db.scalars(
                select(DeclineFactor).where(DeclineFactor.forecast_id == alert.forecast_id)
                .order_by(desc(DeclineFactor.impact_value))
            ).all()
            recommendations = db.scalars(
                select(Recommendation).where(Recommendation.alert_id == alert.id)
                .order_by(Recommendation.priority)
            ).all()
    return render_template(
        "forecasting/detail.html", run=run, forecasts=forecasts,
        alert=alert, factors=factors, recommendations=recommendations,
    )
