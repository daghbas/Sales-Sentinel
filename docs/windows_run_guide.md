# Windows Run Guide

```bat
cd Sales-Sentinel
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-training.txt
python scripts\build_from_redsea.py
pytest -q
python run.py
```

Open `http://127.0.0.1:5000`.

To verify migrations independently:

```bat
set DATABASE_URL=sqlite:///instance/migration_test.db
alembic upgrade head
```
