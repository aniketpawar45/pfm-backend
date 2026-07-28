import httpx
from typing import Dict, Any
from api.core.config import settings
from api.core.database import get_supabase_admin
from api.services.ai_service import AIService


class TelegramService:
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
    FILE_API_URL = f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}"

    @classmethod
    async def process_update(cls, update: Dict[str, Any]):
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]

        # Handle Voice Messages
        if "voice" in message:
            await cls.handle_voice_message(chat_id, message["voice"]["file_id"])
            return

        text = message.get("text", "").strip()
        if not text:
            return

        # Handle Commands
        if text.startswith("/start"):
            await cls.send_message(chat_id,
                                   "Welcome to PFM! Send a voice note or type a natural sentence like: <i>'I spent 400 on a shirt yesterday'</i>.")
        elif text.startswith("/help"):
            await cls.send_message(chat_id,
                                   "Just speak or type your expenses naturally!\nOr use commands: <code>/balance</code>, <code>/recent</code>, <code>/add_account</code>.")
        elif text.startswith("/link"):
            parts = text.split(" ")
            if len(parts) > 1:
                cls.link_chat_id(chat_id, parts[1].strip())
        elif text.startswith("/balance"):
            await cls.handle_balance(chat_id)
        elif text.startswith("/recent"):
            await cls.handle_recent(chat_id)
        elif text.startswith("/add_account"):
            await cls.handle_add_account(chat_id, text)
        elif text.startswith("/"):
            await cls.send_message(chat_id, "Unknown command.")
        else:
            # Handle Natural Language Text (No slash command)
            await cls.process_natural_language(chat_id, text_input=text)

    @classmethod
    async def handle_voice_message(cls, chat_id: int, file_id: str):
        await cls.send_message(chat_id, "🎙️ <i>Listening and processing...</i>")

        async with httpx.AsyncClient() as client:
            file_info_resp = await client.get(f"{cls.TELEGRAM_API_URL}/getFile?file_id={file_id}")
            file_path = file_info_resp.json().get("result", {}).get("file_path")

            if not file_path:
                await cls.send_message(chat_id, "❌ Failed to retrieve audio file.")
                return

            audio_url = f"{cls.FILE_API_URL}/{file_path}"
            audio_resp = await client.get(audio_url)
            audio_bytes = audio_resp.content

        await cls.process_natural_language(chat_id, audio_bytes=audio_bytes)

    @classmethod
    async def process_natural_language(cls, chat_id: int, text_input: str = None, audio_bytes: bytes = None):
        user_id = cls._get_user_id(chat_id)
        if not user_id:
            await cls.send_message(chat_id, "Please link your account first.")
            return

        try:
            parsed_data = AIService.parse_transaction(text_input=text_input, audio_bytes=audio_bytes)

            if isinstance(parsed_data, dict):
                transactions = [parsed_data]
            elif isinstance(parsed_data, list):
                transactions = parsed_data
            else:
                transactions = []

            if not transactions:
                await cls.send_message(chat_id,
                                       "🤖 I couldn't parse that transaction. Please try being a bit more specific.")
                return

            admin_client = get_supabase_admin()

            accs = admin_client.table("accounts").select("id, name").eq("user_id", user_id).is_("deleted_at",
                                                                                                "null").limit(
                1).execute()
            if not accs.data:
                await cls.send_message(chat_id,
                                       "No active account found. Create one first using <code>/add_account</code>.")
                return

            account_id = accs.data[0]["id"]
            acc_name = accs.data[0]["name"]

            success_messages = []
            for tx in transactions:
                if not tx.get("is_transaction", True):
                    continue

                raw_amount = tx.get("amount")
                if raw_amount is None:
                    continue

                amount = float(raw_amount)
                tx_type = tx.get("type", "expense")
                description = tx.get("description", "Uncategorized")
                date = tx.get("date")

                if not date:
                    from datetime import date as dt_date
                    date = dt_date.today().isoformat()

                admin_client.table("transactions").insert({
                    "user_id": user_id,
                    "account_id": account_id,
                    "amount": amount,
                    "type": tx_type,
                    "description": description,
                    "transaction_date": f"{date}T12:00:00Z"
                }).execute()

                symbol = "+" if tx_type == "income" else "-"
                success_messages.append(
                    f"• <b>{tx_type.capitalize()}</b>: <code>{symbol}₹{amount:,.2f}</code> for {description} ({date})"
                )

            if success_messages:
                msg = "✨ <b>Recorded Transactions:</b>\n" + "\n".join(
                    success_messages) + f"\n• <b>Account:</b> {acc_name}"
                await cls.send_message(chat_id, msg)
            else:
                await cls.send_message(chat_id,
                                       "🤖 I caught the details, but you didn't mention an amount. How much was it?")

        except Exception as e:
            print(f"AI Parse Error: {str(e)}")
            await cls.send_message(chat_id, f"🤖 Debug Error: <code>{str(e)}</code>")

    @classmethod
    async def send_message(cls, chat_id: int, text: str):
        async with httpx.AsyncClient() as client:
            await client.post(f"{cls.TELEGRAM_API_URL}/sendMessage",
                              json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

    @classmethod
    def link_chat_id(cls, chat_id: int, code: str):
        admin_client = get_supabase_admin()
        profile = admin_client.table("profiles").select("id").eq("link_code", code).execute()
        if profile.data:
            user_id = profile.data[0]["id"]
            admin_client.table("profiles").update(
                {"telegram_chat_id": chat_id, "link_code": None, "currency": "INR"}).eq("id", user_id).execute()
            accs = admin_client.table("accounts").select("id").eq("user_id", user_id).execute()
            if not accs.data:
                admin_client.table("accounts").insert(
                    {"user_id": user_id, "name": "Primary Account", "type": "checking", "balance": 0.0}).execute()
            httpx.post(f"{cls.TELEGRAM_API_URL}/sendMessage",
                       json={"chat_id": chat_id, "text": "✅ Account linked successfully!"})
        else:
            httpx.post(f"{cls.TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "❌ Invalid code."})

    @classmethod
    async def handle_balance(cls, chat_id: int):
        user_id = cls._get_user_id(chat_id)
        if not user_id: return
        admin_client = get_supabase_admin()
        accounts = admin_client.table("accounts").select("name, balance, type").eq("user_id", user_id).is_("deleted_at",
                                                                                                           "null").execute()
        msg = "<b>Your Account Balances (INR):</b>\n\n"
        total = 0.0
        for acc in accounts.data:
            bal = float(acc["balance"])
            total += bal
            msg += f"• <b>{acc['name']}</b> ({acc['type']}): <code>₹{bal:,.2f}</code>\n"
        msg += f"\n<b>Total Net Worth:</b> <code>₹{total:,.2f}</code>"
        await cls.send_message(chat_id, msg)

    @classmethod
    async def handle_recent(cls, chat_id: int):
        user_id = cls._get_user_id(chat_id)
        if not user_id: return
        admin_client = get_supabase_admin()
        txs = admin_client.table("transactions").select("amount, type, description, transaction_date").eq("user_id",
                                                                                                          user_id).is_(
            "deleted_at", "null").order("transaction_date", desc=True).limit(5).execute()
        msg = "<b>Last 5 Transactions:</b>\n\n"
        for t in txs.data:
            sign = "+" if t["type"] == "income" else "-"
            icon = "🟢" if t["type"] == "income" else "🔴"
            msg += f"{icon} <code>{sign}₹{float(t['amount']):,.2f}</code> - {t['description'] or 'Uncategorized'}\n"
        await cls.send_message(chat_id, msg)

    @classmethod
    async def handle_add_account(cls, chat_id: int, text: str):
        user_id = cls._get_user_id(chat_id)
        if not user_id: return
        parts = text.split(" ")
        if len(parts) < 3:
            await cls.send_message(chat_id, "Usage: <code>/add_account Name Type [Balance]</code>")
            return
        admin_client = get_supabase_admin()
        admin_client.table("accounts").insert({"user_id": user_id, "name": parts[1], "type": parts[2].lower(),
                                               "balance": float(parts[3]) if len(parts) > 3 else 0.0}).execute()
        await cls.send_message(chat_id, f"🎉 Account <b>{parts[1]}</b> created.")

    @classmethod
    def _get_user_id(cls, chat_id: int) -> str | None:
        admin_client = get_supabase_admin()
        profile = admin_client.table("profiles").select("id").eq("telegram_chat_id", chat_id).execute()
        if profile.data: return profile.data[0]["id"]
        return None