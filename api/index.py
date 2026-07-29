from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import auth, accounts, transactions, reports, telegram

app = FastAPI(title="Salary-Anchored PFM Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(accounts.router, prefix="/accounts", tags=["Accounts"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(telegram.router, prefix="/telegram", tags=["Telegram"])

@app.get("/")
def root():
    return {"status": "healthy", "service": "Salary-Anchored PFM Backend"}
