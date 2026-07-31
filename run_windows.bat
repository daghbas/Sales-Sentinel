@echo off
setlocal
py -3.12 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-training.txt
if not exist instance\sales_sentinel.db python scripts\build_from_redsea.py
python run.py
