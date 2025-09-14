# Backend Run
cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard
.venv\Scripts\activate
cd backend
uvicorn app.main:app --reload

- **Swagger docs:** http://localhost:8000/docs


uvicorn app.main:create_app --reload --factory

# Backend Test
cd backend
- **Full:** pytest -q
- **Single file tests:** pytest -q tests/test_parquet_datasets.py
- **Overall Test Coverage:** pytest --cov=app --cov-report=html

While running test set APP_DATA_ADAPTER=stub in command prompt to pass test cases. 
For normal unit tests,
set LIVE_TEST=
set APP_DATA_ADAPTER=stub
pytest -q

live integration test
set APP_DATA_ADAPTER=yahoo
set APP_DEFAULT_UNIVERSE=NIFTY50
set LIVE_TEST=1
pytest -q tests\integration\test_live_scan.py
