from __future__ import annotations

import json
from datetime import datetime, timezone

import psutil
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import desc, func, select, text

from app.database import get_engine, session_scope
from app.models import AuditLog, Branch, ModelRun, Role, SystemHealth, SystemSetting, User
from app.services.audit import write_audit
from app.services.security import current_user, hash_password, login_required, permission_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/users")
@login_required
@permission_required("users.manage")
def users():
    with session_scope() as db:
        items = db.scalars(select(User).order_by(User.created_at.desc())).all()
        roles = db.scalars(select(Role).order_by(Role.id)).all()
        branches = db.scalars(select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)).all()
    return render_template("admin/users.html", users=items, roles=roles, branches=branches)


@admin_bp.post("/users/create")
@login_required
@permission_required("users.manage")
def create_user():
    actor = current_user()
    username = request.form.get("username", "").strip().lower()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role_id = request.form.get("role_id", type=int)
    if not username or len(username) < 3 or not email or "@" not in email or not role_id:
        flash("بيانات المستخدم غير صحيحة / Invalid user data", "error")
        return redirect(url_for("admin.users"))
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.users"))
    with session_scope() as db:
        exists = db.scalar(select(User).where((User.username == username) | (User.email == email)))
        if exists:
            flash("اسم المستخدم أو البريد مستخدم مسبقًا / Username or email already exists", "error")
            return redirect(url_for("admin.users"))
        user = User(
            username=username,
            email=email,
            full_name_ar=request.form.get("full_name_ar", "").strip() or username,
            full_name_en=request.form.get("full_name_en", "").strip() or username,
            password_hash=password_hash,
            role_id=role_id,
            locale=request.form.get("locale", "ar") if request.form.get("locale") in {"ar", "en"} else "ar",
        )
        branch_ids = {int(value) for value in request.form.getlist("branch_ids") if value.isdigit()}
        if branch_ids:
            user.branches = list(db.scalars(select(Branch).where(Branch.id.in_(branch_ids))).all())
        db.add(user); db.flush()
        write_audit(db, "user.create", user_id=actor.id if actor else None, entity_type="user", entity_id=str(user.id))
    flash("تم إنشاء المستخدم / User created", "success")
    return redirect(url_for("admin.users"))


@admin_bp.post("/users/<int:user_id>/toggle")
@login_required
@permission_required("users.manage")
def toggle_user(user_id: int):
    actor = current_user()
    if actor and actor.id == user_id:
        flash("لا يمكن تعطيل حسابك الحالي / You cannot disable your current account", "error")
        return redirect(url_for("admin.users"))
    with session_scope() as db:
        user = db.get(User, user_id)
        if not user:
            flash("المستخدم غير موجود / User not found", "error")
            return redirect(url_for("admin.users"))
        user.is_active = not user.is_active
        write_audit(db, "user.toggle", user_id=actor.id if actor else None, entity_type="user", entity_id=str(user.id), details={"is_active": user.is_active})
    flash("تم تحديث حالة المستخدم / User status updated", "success")
    return redirect(url_for("admin.users"))


@admin_bp.get("/health")
@login_required
@permission_required("system.monitor")
def health():
    checks = []
    with session_scope() as db:
        try:
            db.execute(text("SELECT 1"))
            checks.append({"component": "SQLite", "status": "healthy", "details": "Database query succeeded"})
        except Exception as exc:
            checks.append({"component": "SQLite", "status": "failed", "details": str(exc)})
        model_path = current_app.config["FORECAST_MODEL_PATH"]
        checks.append({
            "component": "Forecast model",
            "status": "healthy" if model_path.exists() else "missing",
            "details": str(model_path),
        })
        last_run = db.scalar(select(ModelRun).order_by(desc(ModelRun.started_at)).limit(1))
        failed_runs = db.scalar(select(func.count(ModelRun.id)).where(ModelRun.status == "failed")) or 0
        logs = db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(30)).all()
        for check in checks:
            row = db.scalar(select(SystemHealth).where(SystemHealth.component == check["component"]))
            if not row:
                row = SystemHealth(component=check["component"], status=check["status"])
                db.add(row)
            row.status = check["status"]
            row.details_json = {"details": check["details"]}
            row.checked_at = datetime.now(timezone.utc)
    resources = {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_available_gb": round(psutil.virtual_memory().available / (1024 ** 3), 2),
        "disk_free_gb": round(psutil.disk_usage(str(current_app.root_path)).free / (1024 ** 3), 2),
    }
    return render_template("admin/health.html", checks=checks, resources=resources, last_run=last_run, failed_runs=failed_runs, logs=logs)


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@permission_required("settings.manage")
def settings():
    actor = current_user()
    if request.method == "POST":
        threshold = request.form.get("decline_threshold", type=float)
        if threshold is None or not 0.01 <= threshold <= 0.50:
            flash("يجب أن يكون حد الانخفاض بين 1% و50% / Threshold must be 1%..50%", "error")
            return redirect(url_for("admin.settings"))
        with session_scope() as db:
            setting = db.scalar(select(SystemSetting).where(SystemSetting.key == "decline_threshold"))
            if not setting:
                setting = SystemSetting(key="decline_threshold", value=str(threshold), value_type="float")
                db.add(setting)
            else:
                setting.value = str(threshold)
            write_audit(db, "settings.update", user_id=actor.id if actor else None, entity_type="setting", entity_id="decline_threshold", details={"value": threshold})
        current_app.config["DECLINE_THRESHOLD"] = threshold
        flash("تم حفظ الإعدادات / Settings saved", "success")
        return redirect(url_for("admin.settings"))
    with session_scope() as db:
        threshold_setting = db.scalar(select(SystemSetting).where(SystemSetting.key == "decline_threshold"))
    threshold = float(threshold_setting.value) if threshold_setting else current_app.config["DECLINE_THRESHOLD"]
    return render_template("admin/settings.html", threshold=threshold)
