# Backend Run
cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard
.venv\Scripts\activate
cd backend
uvicorn app.main:app --reload

uvicorn app.main:create_app --reload --factory

# Backend Test
cd backend
pytest -q

# Single file tests
pytest -q tests/test_parquet_datasets.py