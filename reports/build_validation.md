# Build Validation

The repository is validated through GitHub Actions with Python 3.12:

1. Reconstruct and verify `data/raw/RedSea_Data_Cleaned.csv`.
2. Rebuild the SQLite database and verify 2,695 accepted rows.
3. Apply Alembic to an empty SQLite database.
4. Run data, model, security, route and report tests.
5. Start the Flask application and query `/healthz`.
6. Capture real Chromium screenshots from the running application.

The exact workflow is `.github/workflows/ci.yml`.
