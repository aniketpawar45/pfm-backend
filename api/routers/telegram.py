from fastapi import APIRouter, Request
from api.services.telegram_service import TelegramService

router = APIRouter(prefix="/telegram", tags=["telegram"])

@router.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    
    # We must await this directly. If we use a BackgroundTask, 
    # Vercel will kill the process before it finishes sending the reply.
    await TelegramService.process_update(update)
    
    return {"status": "ok"}