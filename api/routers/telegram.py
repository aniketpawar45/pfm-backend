from fastapi import APIRouter, Request, HTTPException
from api.services.telegram_service import TelegramService

router = APIRouter()

@router.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        body = await request.json()
        await TelegramService.process_update(body)
        return {"ok": True}
    except Exception as e:
        print(f"Webhook Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))