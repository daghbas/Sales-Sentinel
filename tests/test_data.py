from pathlib import Path
import json
import sqlite3


def test_real_data_manifest():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data" / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_rows"] == 2700
    assert manifest["exact_duplicates_removed"] == 5
    assert manifest["accepted_rows"] == 2695
    assert manifest["observed_days"] == 121
    assert manifest["is_synthetic"] is False
    assert manifest["sama_weekly_used_for_training"] is False
    assert manifest["missing_calendar_dates"] == ["2023-09-01", "2023-09-15"]


def test_seed_database_integrity():
    root = Path(__file__).resolve().parents[1]
    connection = sqlite3.connect(root / "instance" / "sales_sentinel.db")
    assert connection.execute("select count(*) from sales").fetchone()[0] == 2695
    assert connection.execute("select count(*) from products").fetchone()[0] == 352
    assert connection.execute("select count(*) from categories").fetchone()[0] == 23
    assert connection.execute("select count(distinct sale_date) from sales").fetchone()[0] == 121
    assert connection.execute("select count(*) from users").fetchone()[0] == 2
    assert connection.execute("select count(*) from forecasts").fetchone()[0] == 37
