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
    async def send_message(cls, chat_id: int, text: str) -> int | None:
        url = f"{cls.get_api_url()}/sendMessage"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                })
                data = response.json()
                if data.get("ok"):
                    return data["result"]["message_id"]
            except Exception as e:
                print(f"Failed to send Telegram message: {str(e)}")
        return None

    @classmethod
    async def edit_message(cls, chat_id: int, message_id: int, text: str):
        if not message_id:
            return
        url = f"{cls.get_api_url()}/editMessageText"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "HTML"
                })
            except Exception as e:
                print(f"Failed to edit Telegram message: {str(e)}")

    @classmethod
    async def process_natural_language(cls, chat_id: int, text_input: str = None, audio_bytes: bytes = None):
        # Step 1: Initialize progress feedback (25%)
        msg_id = await cls.send_message(
            chat_id, 
            "🔄 <b>[25%]</b> Analyzing input & extracting financial data..."
        )

        try:
            # Step 2: Update progress for AI processing (60%)
            if msg_id:
                await cls.edit_message(
                    chat_id, 
                    msg_id, 
                    "🔄 <b>[60%]</b> Processing items through AI model..."
                )

            parsed_data = AIService.parse_transaction(text_input=text_input, audio_bytes=audio_bytes)
            
            # Step 3: Validation & formatting stage (90%)
            if msg_id:
                await cls.edit_message(
                    chat_id, 
                    msg_id, 
                    "🔄 <b>[90%]</b> Validating amounts & ledger formatting..."
                )

            # Handle bulk list items (JSON Array)
            if isinstance(parsed_data, list):
                if not parsed_data:
                    await cls.edit_message(chat_id, msg_id, "🤖 <b>No transactions found</b> in your message.")
                    return
                
                valid_items = [item for item in parsed_data if item.get("is_transaction", True)]
                if not valid_items:
                    await cls.edit_message(
                        chat_id, 
                        msg_id, 
                        "🤖 <b>PFM Assistant</b>\nSend me expenses, income notes, or itemized lists to log them!"
                    )
                    return

                # Check if any item in the list is missing an amount
                missing_amount_items = [item for item in valid_items if item.get("amount") is None]
                if missing_amount_items:
                    item_desc = missing_amount_items[0].get("description") or "transaction"
                    await cls.edit_message(
                        chat_id, 
                        msg_id, 
                        f"⚠️ <b>Incomplete Entry Detected</b>\nI noticed an item ('<code>{item_desc}</code>'), but the amount is missing. Please specify how much."
                    )
                    return

                formatted_list = "\n".join([
                    f"• <b>{item.get('description') or 'Miscellaneous'}</b>: ₹{item.get('amount'):,.2f} <i>({item.get('type', 'expense')})</i>" 
                    for item in valid_items
                ])
                
                final_text = (
                    f"✨ <b>Bulk Transactions Logged Successfully!</b>\n"
                    f"<i>Processed <b>{len(valid_items)}</b> items</i>\n\n"
                    f"{formatted_list}"
                )
                await cls.edit_message(chat_id, msg_id, final_text)
                return

            # Handle single transaction (JSON Object)
            if isinstance(parsed_data, dict):
                if not parsed_data.get("is_transaction", True):
                    await cls.edit_message(
                        chat_id, 
                        msg_id, 
                        "🤖 <b>PFM Assistant</b>\nSend me expenses, income notes, or itemized lists to log them!"
                    )
                    return

                if parsed_data.get("amount") is None:
                    await cls.edit_message(
                        chat_id, 
                        msg_id, 
                        "⚠️ <b>Amount Missing</b>\nI noticed a transaction, but the amount is missing. Please specify how much (e.g., <i>'Paid 500 for lunch'</i>)."
                    )
                    return

                # Fallback description if null
                desc = parsed_data.get("description") or "Miscellaneous"
                amount = parsed_data.get("amount")
                t_type = parsed_data.get("type", "expense")
                t_date = parsed_data.get("date", "Today")

                final_text = (
                    f"✨ <b>Transaction Logged Successfully</b>\n\n"
                    f"🔹 <b>Description:</b> {desc}\n"
                    f"💰 <b>Amount:</b> ₹{amount:,.2f}\n"
                    f"📂 <b>Type:</b> {t_type.capitalize()}\n"
                    f"📅 <b>Date:</b> {t_date}"
                )
                await cls.edit_message(chat_id, msg_id, final_text)
                return
            
        except Exception as e:
            error_msg = f"❌ <b>Error Occurred</b>\n<code>{str(e)}</code>"
            if msg_id:
                await cls.edit_message(chat_id, msg_id, error_msg)
            else:
                await cls.send_message(chat_id, error_msg)

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