from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import desc, select

from app.database import session_scope
from app.models import ImportJob
from app.services.audit import write_audit
from app.services.import_service import import_sales
from app.services.security import current_user, login_required, permission_required, safe_filename

imports_bp = Blueprint("imports", __name__, url_prefix="/imports")


@imports_bp.route("/", methods=["GET", "POST"])
@login_required
@permission_required("sales.import")
def index():
    user = current_user()
    if request.method == "POST":
        upload = request.files.get("file")
        if not upload or not upload.filename:
            flash("اختر ملف CSV أو XLSX / Select a CSV or XLSX file", "error")
            return redirect(url_for("imports.index"))
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xlsm"}:
            flash("نوع الملف غير مسموح / Unsupported file type", "error")
            return redirect(url_for("imports.index"))
        filename = safe_filename(upload.filename)
        target = current_app.config["UPLOAD_DIR"] / filename
        upload.save(target)
        with session_scope() as db:
            try:
                result = import_sales(db, target, user_id=user.id if user else None, is_demo=False)
                write_audit(db, "sales.import", user_id=user.id if user else None, entity_type="import_job", entity_id=str(result.job.id),
                            details={"accepted": result.job.accepted_rows, "rejected": result.job.rejected_rows})
                if result.errors:
                    flash(f"تم الاستيراد مع رفض {len(result.errors)} صفًا / Imported with {len(result.errors)} rejected rows", "warning")
                else:
                    flash("تم استيراد البيانات بنجاح / Data imported successfully", "success")
            except Exception as exc:
                flash(str(exc), "error")
        return redirect(url_for("imports.index"))
    with session_scope() as db:
        jobs = db.scalars(select(ImportJob).order_by(desc(ImportJob.created_at)).limit(30)).all()
    return render_template("imports/index.html", jobs=jobs)
