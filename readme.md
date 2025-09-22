# Backend Run
cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard
.venv\Scripts\activate
cd backend
set APP_DISABLE_ALEMBIC=1
uvicorn app.main:app --reload

### New way to start application backend
cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard
.venv\Scripts\activate
set APP_DISABLE_ALEMBIC=1
python run_uvicorn.py

set BACKFILL_ON_START=0  off   BACKFILL_ON_START=1 on

### Option A: run Alembic once, then start dev
set APP_DISABLE_ALEMBIC=0
alembic upgrade head
set APP_DISABLE_ALEMBIC=1
(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend>alembic heads
20250912_0002 (head)
20250921_01 (head)

(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend>alembic merge -m "Merge heads 20250921_01 & 20250912_0002" 20250921_01 20250912_0002


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

# Generate pydantic models. These will be used in front communication.

(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend> datamodel-codegen --input ..\contracts/openapi.yaml --input-file-type openapi --output app/schemas/generated/models.py --output-model-type pydantic_v2.BaseModel --target-python-version 3.11 --use-double-quotes --use-standard-collections --enum-field-as-literal all --collapse-root-models --encoding utf-8

# This is to auto generate code from open API frontend. 
D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\frontend>npx orval --config .\orval.config.ts


