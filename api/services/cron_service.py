import os
from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client
import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
IST = ZoneInfo("Asia/Kolkata")

async def run_daily_subscription_checks():
    today_ist = datetime.now(IST).date().isoformat()
    
    response = supabase.table("subscriptions").select("*").eq("status", "active").eq("next_billing_date", today_ist).execute()
    
    if not response.data:
        return {"processed": 0, "message": "No subscriptions due today in IST."}

    count = 0
    async with httpx.AsyncClient() as client:
        for sub in response.data:
            chat_id = sub["chat_id"]
            name = sub["name"]
            amount = sub["amount"]
            
            msg = f"Reminder: Your subscription for '{name}' (₹{amount:.2f}) is due today!"
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            await client.post(url, json={"chat_id": chat_id, "text": msg})
            count += 1

    return {"processed": count, "status": "success"}
