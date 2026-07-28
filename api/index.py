from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import auth, accounts, transactions, reports, telegram

app = FastAPI(title="PFM API", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(telegram.router)

@app.get("/")
def root(): return {"status": "PFM API is running"}
