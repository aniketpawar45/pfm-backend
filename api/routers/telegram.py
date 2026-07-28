from fastapi import APIRouter, Request, BackgroundTasks
from api.services.telegram_service import TelegramService

router = APIRouter(prefix="/telegram", tags=["telegram"])

@router.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(TelegramService.process_update, await request.json())
    return {"status": "ok"}
