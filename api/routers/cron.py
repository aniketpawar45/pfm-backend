import os
from fastapi import APIRouter, Header, HTTPException
from api.services.db_service import DBService
from api.services.telegram_service import TelegramService

router = APIRouter()

@router.get("/daily")
def run_daily_cron(authorization: str = Header(None)):
    cron_secret = os.getenv("CRON_SECRET")
    
    # Secure the endpoint
    if not cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET environment variable is missing.")
    
    expected_header = f"Bearer {cron_secret}"
    if authorization != expected_header:
        raise HTTPException(status_code=401, detail="Unauthorized request to cron endpoint.")

    # Process all recurring bills & budget alerts
    alerts = DBService.process_daily_cron()
    
    # Broadcast to Telegram
    for chat_id, message in alerts:
        try:
            TelegramService.send_message(chat_id, message)
        except Exception as e:
            print(f"Failed to send cron alert to {chat_id}: {e}")

    return {"status": "success", "processed_alerts": len(alerts)}
