from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.models import Branch, Category, CustomerSegment, ImportJob, Product, Promotion, Region, Sale


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

MINIMUM_COLUMNS = {"date", "product", "category", "quantity", "net_sales", "unit_price", "discount_percent", "channel"}

ALIASES = {
    "trx date": "date",
    "trx number": "transaction_number",
    "sales channel": "channel",
    "type": "transaction_type",
    "item code": "sku",
    "item desc": "product",
    "family": "family",
    "class": "category",
    "subclass": "subclass",
    "franchise": "franchise",
    "quantity": "quantity",
    "unit price": "unit_price",
    "discount amount": "discount_amount",
    "discount amount(%)": "discount_percent",
    "net amount": "net_sales",
    "vat amount": "vat_amount",
    "total amount": "total_amount",
    "org": "org",
    "التاريخ": "date",
    "المنتج": "product",
    "الفئة": "category",
    "الكمية": "quantity",
    "صافي المبيعات": "net_sales",
    "السعر": "unit_price",
    "الخصم": "discount_percent",
    "قناة البيع": "channel",
    "date": "date",
    "product": "product",
    "category": "category",
    "quantity": "quantity",
    "net_sales": "net_sales",
    "sales": "net_sales",
    "unit_price": "unit_price",
    "price": "unit_price",
    "discount_percent": "discount_percent",
    "discount": "discount_percent",
    "channel": "channel",
    "branch": "branch",
    "region": "region",
    "transaction_number": "transaction_number",
    "transaction_type": "transaction_type",
    "stock_quantity": "stock_quantity",
    "customer_segment": "customer_segment",
    "promotion": "promotion",
    "seasonal_factor": "seasonal_factor",
}


@dataclass
class ImportResult:
    job: ImportJob
    errors: list[dict]


def read_sales_file(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(path, engine="openpyxl")
    else:
        raise ValueError("Only CSV and XLSX files are supported")
    normalized = []
    for column in frame.columns:
        key = str(column).strip().lower()
        normalized.append(ALIASES.get(key, key.replace(" ", "_")))
    frame.columns = normalized
    missing = MINIMUM_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
    return frame


def clean_sales_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    data = frame.copy()
    before = len(data)
    data = data.drop_duplicates().reset_index(drop=True)
    duplicate_count = before - len(data)
    errors: list[dict] = []
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date
    defaults = {
        "transaction_number": "UNSPECIFIED",
        "transaction_type": "INV",
        "sku": "",
        "family": "",
        "subclass": "",
        "franchise": "",
        "discount_amount": 0.0,
        "vat_amount": 0.0,
        "total_amount": np.nan,
        "branch": "Jeddah Tahlia",
        "region": "Western",
        "org": "",
        "stock_quantity": np.nan,
        "customer_segment": "Unspecified",
        "promotion": "",
        "seasonal_factor": 1.0,
    }
    for column, value in defaults.items():
        if column not in data.columns:
            data[column] = value
    numeric = [
        "quantity", "net_sales", "unit_price", "discount_amount", "discount_percent",
        "vat_amount", "total_amount", "stock_quantity", "seasonal_factor",
    ]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["transaction_type"] = data["transaction_type"].fillna("INV").astype(str).str.upper().str.strip()
    data["total_amount"] = data["total_amount"].fillna(data["net_sales"] + data["vat_amount"])
    data["gross_sales"] = data["quantity"] * data["unit_price"]
    for index, row in data.iterrows():
        row_errors: list[str] = []
        if pd.isna(row["date"]):
            row_errors.append("invalid date")
        for column in ["product", "category", "channel"]:
            if pd.isna(row[column]) or not str(row[column]).strip():
                row_errors.append(f"missing {column}")
        if pd.isna(row["quantity"]):
            row_errors.append("invalid quantity")
        if pd.isna(row["net_sales"]):
            row_errors.append("invalid net_sales")
        if pd.isna(row["unit_price"]) or row["unit_price"] < 0:
            row_errors.append("unit_price must be non-negative")
        if pd.isna(row["discount_percent"]) or not 0 <= row["discount_percent"] <= 100:
            row_errors.append("discount must be 0..100")
        if pd.isna(row["seasonal_factor"]) or not 0.1 <= row["seasonal_factor"] <= 5:
            row_errors.append("seasonal_factor out of range")
        if row_errors:
            errors.append({"row": index + 2, "errors": row_errors})
    invalid_indexes = {error["row"] - 2 for error in errors}
    data = data[~data.index.isin(invalid_indexes)].copy()
    text_columns = [
        "transaction_number", "transaction_type", "sku", "product", "category", "channel",
        "family", "subclass", "franchise", "branch", "region", "org", "customer_segment", "promotion",
    ]
    for column in text_columns:
        data[column] = data[column].fillna("").astype(str).str.strip()
    data["sku"] = data["sku"].where(data["sku"] != "", data["product"])
    data["is_promotion"] = (data["discount_percent"] > 0) | (data["discount_amount"].abs() > 0)
    if duplicate_count:
        errors.insert(0, {"row": 0, "errors": [f"removed {duplicate_count} exact duplicate rows"]})
    return data.reset_index(drop=True), errors


def _stable_code(prefix: str, value: str, size: int = 12) -> str:
    return f"{prefix}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:size]}"


def _get_or_create_region(db, name: str) -> Region:  # type: ignore[no-untyped-def]
    region = db.scalar(select(Region).where((Region.name_ar == name) | (Region.name_en == name) | (Region.code == name)))
    if not region:
        region = Region(code=_stable_code("REG", name, 8), name_ar=name, name_en=name)
        db.add(region)
        db.flush()
    return region


def _get_or_create_branch(db, name: str, region: Region) -> Branch:  # type: ignore[no-untyped-def]
    branch = db.scalar(select(Branch).where((Branch.name_ar == name) | (Branch.name_en == name) | (Branch.code == name)))
    if not branch:
        branch = Branch(code=_stable_code("BR", f"{name}:{region.id}", 8), name_ar=name, name_en=name,
                        city_ar="جدة", city_en="Jeddah", region_id=region.id)
        db.add(branch)
        db.flush()
    return branch


def _get_or_create_category(db, name: str) -> Category:  # type: ignore[no-untyped-def]
    item = db.scalar(select(Category).where((Category.name_ar == name) | (Category.name_en == name) | (Category.code == name)))
    if not item:
        item = Category(code=_stable_code("CAT", name, 10), name_ar=name, name_en=name)
        db.add(item)
        db.flush()
    return item


def _get_or_create_product(db, sku: str, name: str, category: Category, price: float) -> Product:  # type: ignore[no-untyped-def]
    item = db.scalar(select(Product).where(Product.sku == sku))
    if not item:
        item = Product(sku=sku[:50], name_ar=name[:150], name_en=name[:150], category_id=category.id,
                       base_price=Decimal(str(round(max(price, 0.0), 2))))
        db.add(item)
        db.flush()
    return item


def _row_hash(row: pd.Series) -> str:
    values = [
        row["date"].isoformat(), str(row["transaction_number"]), str(row["transaction_type"]),
        str(row["sku"]), str(row["quantity"]), str(row["unit_price"]), str(row["net_sales"]),
        str(row["channel"]), str(row.name),
    ]
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def import_sales(db, path: Path, user_id: int | None = None, is_demo: bool = False) -> ImportResult:  # type: ignore[no-untyped-def]
    job = ImportJob(filename=path.name, file_sha256=sha256_file(path), status="processing", created_by_id=user_id)
    db.add(job)
    db.flush()
    try:
        raw = read_sales_file(path)
        clean, errors = clean_sales_frame(raw)
        job.total_rows = len(raw)
        actual_rejections = [error for error in errors if error.get("row", 0) > 0]
        job.rejected_rows = len(actual_rejections)
        segment = db.scalar(select(CustomerSegment).where(CustomerSegment.code == "unspecified"))
        if not segment:
            segment = CustomerSegment(code="unspecified", name_ar="غير محدد", name_en="Unspecified")
            db.add(segment)
            db.flush()
        for _, row in clean.iterrows():
            region = _get_or_create_region(db, row["region"] or "Western")
            branch = _get_or_create_branch(db, row["branch"] or "Jeddah Tahlia", region)
            category = _get_or_create_category(db, row["category"])
            product = _get_or_create_product(db, row["sku"], row["product"], category, float(row["unit_price"]))
            promotion = None
            if bool(row["is_promotion"]):
                promotion = db.scalar(select(Promotion).where(Promotion.code == "discounted-sale"))
                if not promotion:
                    promotion = Promotion(code="discounted-sale", name_ar="بيع بخصم", name_en="Discounted sale",
                                          start_date=date(2023, 1, 1), end_date=date(2030, 12, 31), discount_percent=0.0)
                    db.add(promotion)
                    db.flush()
            row_hash = _row_hash(row)
            if db.scalar(select(Sale.id).where(Sale.source_row_hash == row_hash)):
                continue
            db.add(Sale(
                sale_date=row["date"], transaction_number=str(row["transaction_number"]),
                transaction_type=str(row["transaction_type"]), branch_id=branch.id, product_id=product.id,
                customer_segment_id=segment.id, promotion_id=promotion.id if promotion else None,
                channel=str(row["channel"]), family=str(row["family"]) or None,
                subclass=str(row["subclass"]) or None, franchise=str(row["franchise"]) or None,
                quantity=int(row["quantity"]), unit_price=Decimal(str(round(float(row["unit_price"]), 2))),
                discount_amount=Decimal(str(round(float(row["discount_amount"]), 2))),
                discount_percent=float(row["discount_percent"]),
                gross_sales=Decimal(str(round(float(row["gross_sales"]), 2))),
                net_sales=Decimal(str(round(float(row["net_sales"]), 2))),
                vat_amount=Decimal(str(round(float(row["vat_amount"]), 2))),
                total_amount=Decimal(str(round(float(row["total_amount"]), 2))),
                stock_quantity=None if pd.isna(row["stock_quantity"]) else int(row["stock_quantity"]),
                inventory_available=not pd.isna(row["stock_quantity"]),
                is_promotion=bool(row["is_promotion"]), seasonal_factor=float(row["seasonal_factor"]),
                is_demo=is_demo, source_row_hash=row_hash, source_import_id=job.id,
            ))
        job.accepted_rows = len(clean)
        job.error_details = {"notes": errors[:100]}
        job.status = "completed" if not actual_rejections else "completed_with_errors"
        return ImportResult(job=job, errors=errors)
    except Exception as exc:
        job.status = "failed"
        job.error_details = {"message": str(exc)}
        raise
