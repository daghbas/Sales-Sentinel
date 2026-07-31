from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from app import create_app
from app.config import Config
from app.database import SessionLocal


@pytest.fixture()
def app(tmp_path: Path):
    source = Path(__file__).resolve().parents[1] / "instance" / "sales_sentinel.db"
    database = tmp_path / "test.db"
    shutil.copy2(source, database)

    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret-key"
        DATABASE_URL = f"sqlite:///{database}"
        SESSION_COOKIE_SECURE = False
        UPLOAD_DIR = tmp_path / "uploads"
        REPORT_DIR = tmp_path / "reports"

    app = create_app(TestConfig)
    yield app
    SessionLocal.remove()


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf_from(client, path="/auth/login") -> str:
    client.get(path)
    with client.session_transaction() as session:
        return session["csrf_token"]


def login(client, username="admin", password="Admin@2026!"):
    token = csrf_from(client)
    return client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=True,
    )
