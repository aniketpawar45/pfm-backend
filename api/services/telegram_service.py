import httpx
from api.core.config import settings
from api.services.ai_service import AIService

class TelegramService:
    @classmethod
    def get_api_url(cls) -> str:
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        if not token or not token.strip():
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing or empty.")
        return f"https://api.telegram.org/bot{token.strip('\" ')}"

    @classmethod
    async def send_message(cls, chat_id: int, text: str):
        url = f"{cls.get_api_url()}/sendMessage"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                })
            except Exception as e:
                print(f"Failed to send Telegram message: {str(e)}")

    @classmethod
    async def process_natural_language(cls, chat_id: int, text_input: str = None, audio_bytes: bytes = None):
        try:
            parsed_data = AIService.parse_transaction(text_input=text_input, audio_bytes=audio_bytes)
            
            # Handle non-financial chatter
            if isinstance(parsed_data, dict) and not parsed_data.get("is_transaction", True):
                await cls.send_message(chat_id, "🤖 I'm your PFM assistant. Send me expenses or income notes (e.g., 'Spent 500 on lunch') or grocery lists to log them!")
                return

            # Handle missing amount cases
            if isinstance(parsed_data, dict) and parsed_data.get("amount") is None:
                await cls.send_message(chat_id, "⚠️ I noticed a transaction, but the amount is missing. Please specify how much (e.g., 'Paid 500 for lunch').")
                return

            # Format confirmation message back to user (ready for database insertion)
            await cls.send_message(chat_id, f"✅ Successfully processed transaction!\n<pre>{parsed_data}</pre>")
            
        except Exception as e:
            await cls.send_message(chat_id, f"🤖 Debug Error: <code>{str(e)}</code>")

    @classmethod
    async def process_update(cls, update: dict):
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text")
        voice = message.get("voice")

        audio_bytes = None
        if voice:
            file_id = voice["file_id"]
            async with httpx.AsyncClient() as client:
                file_info_resp = await client.get(f"{cls.get_api_url()}/getFile?file_id={file_id}")
                file_path = file_info_resp.json()["result"]["file_path"]
                file_resp = await client.get(f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}")
                audio_bytes = file_resp.content

        if text or audio_bytes:
            await cls.process_natural_language(chat_id, text_input=text, audio_bytes=audio_bytes)