from __future__ import annotations

from flask import Blueprint, Response, render_template, request
from sqlalchemy import desc, select

from app.database import session_scope
from app.models import ModelRun
from app.services.report_service import export_csv, export_excel, export_pdf
from app.services.security import login_required, permission_required

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.get("/")
@login_required
@permission_required("reports.view")
def index():
    with session_scope() as db:
        runs = db.scalars(select(ModelRun).where(ModelRun.status == "completed").order_by(desc(ModelRun.completed_at)).limit(50)).all()
    return render_template("reports/index.html", runs=runs)


@reports_bp.get("/<int:run_id>.<fmt>")
@login_required
@permission_required("reports.download")
def download(run_id: int, fmt: str):
    with session_scope() as db:
        if fmt == "csv":
            payload, mime = export_csv(db, run_id), "text/csv; charset=utf-8"
        elif fmt == "xlsx":
            payload, mime = export_excel(db, run_id), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt == "pdf":
            payload, mime = export_pdf(db, run_id, request.args.get("locale", "en")), "application/pdf"
        else:
            return Response("Unsupported format", status=400)
    response = Response(payload, mimetype=mime)
    response.headers["Content-Disposition"] = f'attachment; filename="forecast-{run_id}.{fmt}"'
    return response
