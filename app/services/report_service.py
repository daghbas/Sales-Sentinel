from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select

from app.models import Alert, Forecast, ModelRun, Sale


def forecast_dataframe(db, run_id: int) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    run = db.get(ModelRun, run_id)
    if not run:
        raise ValueError("Model run not found")
    rows = db.scalars(select(Forecast).where(Forecast.model_run_id == run_id).order_by(Forecast.forecast_date)).all()
    return pd.DataFrame([{
        "date": row.forecast_date.isoformat(),
        "predicted_sales_sar": float(row.predicted_sales),
        "lower_bound_sar": float(row.lower_bound),
        "upper_bound_sar": float(row.upper_bound),
        "baseline_sales_sar": float(row.baseline_sales),
        "decline_probability": row.decline_probability,
        "decline_percent": row.decline_percent,
    } for row in rows])


def export_csv(db, run_id: int) -> bytes:  # type: ignore[no-untyped-def]
    return forecast_dataframe(db, run_id).to_csv(index=False).encode("utf-8-sig")


def export_excel(db, run_id: int) -> bytes:  # type: ignore[no-untyped-def]
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        forecast_dataframe(db, run_id).to_excel(writer, sheet_name="Forecast", index=False)
    return buffer.getvalue()


def export_pdf(db, run_id: int, locale: str = "en") -> bytes:  # type: ignore[no-untyped-def]
    frame = forecast_dataframe(db, run_id)
    run = db.get(ModelRun, run_id)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title = "Sales Forecast Report" if locale == "en" else "Sales Forecast Report / تقرير توقعات المبيعات"
    story = [Paragraph(title, styles["Title"]), Spacer(1, 8)]
    story.append(Paragraph(f"Model: {run.model_name} | Horizon: {run.horizon_days} days | Generated: {datetime.utcnow().isoformat(timespec='minutes')} UTC", styles["BodyText"]))
    story.append(Spacer(1, 10))
    headers = ["Date", "Forecast SAR", "Lower", "Upper", "Baseline", "Decline %", "Risk"]
    data = [headers] + [[
        row["date"], f"{row['predicted_sales_sar']:,.2f}", f"{row['lower_bound_sar']:,.2f}",
        f"{row['upper_bound_sar']:,.2f}", f"{row['baseline_sales_sar']:,.2f}",
        f"{row['decline_percent']:.1%}", f"{row['decline_probability']:.1%}",
    ] for _, row in frame.head(90).iterrows()]
    table = Table(data, repeatRows=1, colWidths=[25*mm, 27*mm, 23*mm, 23*mm, 25*mm, 22*mm, 20*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#17352c")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#c9d3ce")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7.5),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f4f7f5")]),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
    ]))
    story.extend([table, Spacer(1, 8), Paragraph("Decision-support output; not a guarantee of business results.", styles["Italic"])])
    doc.build(story)
    return buffer.getvalue()
