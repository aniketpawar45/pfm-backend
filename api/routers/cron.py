import os
from fastapi import APIRouter, Header, HTTPException
from api.services.cron_service import run_daily_subscription_checks

router = APIRouter()

@router.get("/daily")
async def trigger_daily_cron(authorization: str = Header(None)):
    cron_secret = os.getenv("CRON_SECRET")
    
    # Verify Vercel Cron Secret if configured
    if cron_secret:
        expected_auth = f"Bearer {cron_secret}"
        if authorization != expected_auth:
            raise HTTPException(status_code=401, detail="Unauthorized cron execution")
            
    result = await run_daily_subscription_checks()
    return result
