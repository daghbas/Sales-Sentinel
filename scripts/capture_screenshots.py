from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("APP_URL", "http://127.0.0.1:5000")
OUTPUT = Path(__file__).resolve().parents[1] / "screenshots"
OUTPUT.mkdir(parents=True, exist_ok=True)


def shot(page, name: str):
    page.screenshot(path=str(OUTPUT / name), full_page=True)


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page = context.new_page()
        page.goto(f"{BASE_URL}/auth/login", wait_until="networkidle")
        shot(page, "01-login-ar.png")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "wrong-password")
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        shot(page, "02-login-error-red-card.png")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "Admin@2026!")
        page.click('button[type="submit"]')
        page.wait_for_url(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")
        shot(page, "03-dashboard-ar.png")
        page.goto(f"{BASE_URL}/sales/", wait_until="networkidle")
        shot(page, "04-daily-sales-ar.png")
        page.goto(f"{BASE_URL}/forecasts/", wait_until="networkidle")
        shot(page, "05-forecasts-ar.png")
        page.check('input[name="horizon"][value="90"]')
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")
        shot(page, "06-forecast-90-blocked.png")
        page.goto(f"{BASE_URL}/reports/", wait_until="networkidle")
        shot(page, "07-reports-ar.png")
        page.goto(f"{BASE_URL}/admin/users", wait_until="networkidle")
        shot(page, "08-users-rbac-ar.png")
        page.goto(f"{BASE_URL}/admin/health", wait_until="networkidle")
        shot(page, "09-system-health-ar.png")
        page.goto(f"{BASE_URL}/locale/en?next=/", wait_until="networkidle")
        shot(page, "10-dashboard-en.png")
        browser.close()


if __name__ == "__main__":
    main()
