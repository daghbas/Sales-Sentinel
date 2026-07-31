from io import BytesIO

from conftest import csrf_from, login


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_login_success_and_dashboard(client):
    response = login(client)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Sales Sentinel" in text or "حارس المبيعات" in text
    assert "2,695" in text


def test_login_error_card(client):
    token = csrf_from(client)
    response = client.post("/auth/login", data={"username": "admin", "password": "wrong-password", "csrf_token": token})
    assert response.status_code == 401
    assert "flash error" in response.get_data(as_text=True)


def test_analyst_cannot_manage_users(client):
    login(client, "analyst", "Analyst@2026!")
    assert client.get("/admin/users").status_code == 403


def test_sales_and_forecasts_pages(client):
    login(client)
    assert client.get("/sales/").status_code == 200
    assert client.get("/forecasts/").status_code == 200
    assert client.get("/forecasts/1").status_code == 200


def test_90_day_forecast_is_blocked(client):
    login(client)
    with client.session_transaction() as session:
        token = session["csrf_token"]
    response = client.post("/forecasts/", data={"horizon": "90", "branch_id": "", "channel": "", "csrf_token": token}, follow_redirects=True)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "365" in text or "90 يوم" in text
    assert "flash error" in text


def test_report_exports(client):
    login(client)
    for extension in ("csv", "xlsx", "pdf"):
        response = client.get(f"/reports/1.{extension}")
        assert response.status_code == 200
        assert len(response.data) > 100


def test_invalid_upload_type_is_rejected(client):
    login(client)
    with client.session_transaction() as session:
        token = session["csrf_token"]
    response = client.post(
        "/imports/",
        data={"csrf_token": token, "file": (BytesIO(b"bad"), "bad.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Unsupported file type" in response.get_data(as_text=True)
