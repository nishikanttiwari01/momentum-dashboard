# Backend Run
cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard
.venv\Scripts\activate
cd backend
set APP_DISABLE_ALEMBIC=1
uvicorn app.main:app --reload

set APP_DISABLE_ALEMBIC=0
python run_uvicorn.py  # temporarily change reload=True -> False in the file

### Option A: run Alembic once, then start dev
set APP_DISABLE_ALEMBIC=0
alembic upgrade head
set APP_DISABLE_ALEMBIC=1
python run_uvicorn.py
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

# Frontend Run
cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\frontend
npm run dev


# backfill 1y (252 TD) for your default universe
python -m app.cli.backfill
# or explicitly
python -m app.cli.backfill --days 252 --universe NIFTY500

# FGenerate pydantic models. These will be used in front communication.

(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend> datamodel-codegen --input ..\contracts/openapi.yaml --input-file-type openapi --output app/schemas/generated/models.py --output-model-type pydantic_v2.BaseModel --target-python-version 3.11 --use-double-quotes --use-standard-collections --enum-field-as-literal all --collapse-root-models --encoding utf-8

