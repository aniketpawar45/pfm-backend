import httpx
from typing import Dict, Any
from api.core.config import settings
from api.core.database import get_supabase_admin

class TelegramService:
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

    @classmethod
    async def process_update(cls, update: Dict[str, Any]):
        message = update.get("message")
        if not message: return
        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()

        if text.startswith("/start"):
            await cls.send_message(chat_id, "Welcome to PFM! Use `/link <CODE>` to connect.")
        elif text.startswith("/link"):
            parts = text.split(" ")
            if len(parts) > 1: cls.link_chat_id(chat_id, parts[1].strip())
        elif text.startswith("/balance"):
            await cls.handle_balance(chat_id)

    @classmethod
    async def send_message(cls, chat_id: int, text: str):
        async with httpx.AsyncClient() as client:
            await client.post(f"{cls.TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

    @classmethod
    def link_chat_id(cls, chat_id: int, code: str):
        admin_client = get_supabase_admin()
        profile = admin_client.table("profiles").select("id").eq("link_code", code).execute()
        if profile.data:
            admin_client.table("profiles").update({"telegram_chat_id": chat_id, "link_code": None}).eq("id", profile.data[0]["id"]).execute()
            httpx.post(f"{cls.TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "Account Linked!"})

    @classmethod
    async def handle_balance(cls, chat_id: int):
        admin_client = get_supabase_admin()
        profile = admin_client.table("profiles").select("id").eq("telegram_chat_id", chat_id).execute()
        if profile.data:
            accounts = admin_client.table("accounts").select("name, balance").eq("user_id", profile.data[0]["id"]).execute()
            msg = "**Balances:**\n" + "\n".join([f"{a['name']}: ${a['balance']}" for a in accounts.data])
            await cls.send_message(chat_id, msg)
