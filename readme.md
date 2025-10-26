
# Overview
This trading app is for indian stock analysis solely for personal use. The intend is to use for swing trading that is quick gain in few days to a few week time. 
I have another full time job hence may or may not be running this app everyday. The application should be generate quality alerts for buying a stock. ANd once trade is on , it should give quality alert to hold or sell it to either book profit or stop losss. 
### Features
- **Daily Scan:** This runs whenever app is launch and backfill OHLV parquet writing since last trading date.(backfill.py)
- **Intraday Scan:** This runsevery 15 min and writes OHLV parquet in intraday folder for current day.(scheduler.py)
- **Dashboard:** Contains top gainer,losers and Screener table containing all the stocks with OHLV details 
- **Momentum Score:** This is calculated internally based on several factors to determine potential stocks for buying. COuld rang from 0 to 100. Stock with score of 70 and more are most likely to be bought.
- **Right Drawer:** A right window when clicked on any stock in screener table. Shows next action and many other OHLV related details.
- **Next Action:** Next action is determined to  guide what should be done with the stock like whether to buy it or hold it or simply ignore it etc.
- **Book Trade:** In right drawer a stocked caan be booked for trading. Although application actually book a trade it is just for reference and alerting purpose.
- **Alerts:** Alerts can be intraday or end of day (EOD) called from scheduler or backfill code. It generate around 12 different types of alerts related to buy and sell of stocks. There is special alert sent via email called email digest which contains top losers, top gainers, application created top stocks by score and all active trades.
- **Trades Page:** This page shows all booked trades.
- **Alert Page:** This page shows all fired alerts.

### AI prompt
Analyse attached project zip like an expert python and react developer with 15 years of expereince. No guessing, go through the code before you stop. 

### Goal
10 % percent gain per month with minimal trade consisting of 3 to 5 stocks ideally.

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

set BACKFILL_ON_START=0  off   set BACKFILL_ON_START=1 on

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

### To get all the detail JSON of stocks in one go
(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend\app\api>python fetch_details.py

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

# This is to send email for any trading day 
(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard\backend>python -m app.notifs.email_digest -d 2025-09-24 --save-html digest.html

# Backend install
cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard
.venv\Scripts\activate
cd backend
pip install -r requirements.txt



(.venv) D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard>D:/WORK/NEW_STOCK_DASHBOARD/momentum-dashboard/.venv/Scripts/python.exe d:/WORK/NEW_STOCK_DASHBOARD/momentum-dashboard/backend/util/build_master_from_equity_l.py d:/WORK/NEW_STOCK_DASHBOARD/momentum-dashboard/backend/util/nse_master.csv