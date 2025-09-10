cd /d D:\WORK\NEW_STOCK_DASHBOARD\momentum-dashboard
.venv\Scripts\activate
backend/uvicorn app.main:app --reload

# for test
cd backend
pytest -q