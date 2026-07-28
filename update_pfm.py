import os
from pathlib import Path

# ==========================================
# FILE CONTENTS TO WRITE
# ==========================================

REQUIREMENTS = r'''fastapi>=0.111.0
uvicorn>=0.30.1
supabase>=2.5.0
httpx>=0.27.0
pydantic>=2.7.4
pydantic-settings>=2.3.4
python-jose>=3.3.0
python-multipart>=0.0.9
google-generativeai>=0.7.2
pytz>=2024.1
'''

CONFIG_PY = r'''from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    TELEGRAM_BOT_TOKEN: str
    JWT_SECRET: str
    GEMINI_API_KEY: str
    ENVIRONMENT: str = "production"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
'''

AI_SERVICE_PY = r'''import json
import google.generativeai as genai
from datetime import datetime
import pytz
from api.core.config import settings

# Configure Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

class AIService:
    @staticmethod
    def parse_transaction(text_input: str = None, audio_bytes: bytes = None) -> dict:
        """
        Parses natural language text or audio to extract transaction data.
        Returns a dictionary: {"amount": float, "type": "income"|"expense", "description": str, "date": "YYYY-MM-DD"}
        """
        # Inject current context so AI knows what "yesterday" means
        ist = pytz.timezone('Asia/Kolkata')
        current_date = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")

        prompt = f"""
        You are a financial parsing assistant. The current date and time in India (IST) is {current_date}.
        Analyze the user's input and extract the financial transaction.
        
        Rules:
        1. Determine if it is an 'income' or 'expense'.
        2. Extract the absolute numerical amount.
        3. Extract the item or description.
        4. Calculate the exact date (YYYY-MM-DD) based on words like 'yesterday', 'today', or specific dates mentioned. If not mentioned, use today's date.
        
        Output EXCLUSIVELY as a valid JSON object with the following exact keys: 
        "amount" (number), "type" (string: "income" or "expense"), "description" (string), "date" (string: YYYY-MM-DD).
        Do not include markdown formatting, backticks, or any other text.
        """

        contents = [prompt]

        if audio_bytes:
            contents.append({
                "mime_type": "audio/ogg",
                "data": audio_bytes
            })
        elif text_input:
            contents.append(f"User input: {text_input}")
        else:
            raise ValueError("Must provide text or audio")

        response = model.generate_content(
            contents,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1 # Low temperature for factual extraction
            )
        )

        try:
            # Strip potential markdown formatting if Gemini disobeys instructions
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse AI response into JSON: {response.text}")
'''

TELEGRAM_SERVICE_PY = r'''import httpx
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
            await cls.send_message(chat_id, "Welcome to PFM! Send a voice note or type a natural sentence like: *'I spent 400 on a shirt yesterday'*.")
        elif text.startswith("/help"):
            await cls.send_message(chat_id, "Just speak or type your expenses naturally!\nOr use commands: `/balance`, `/recent`, `/add_account`.")
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
        await cls.send_message(chat_id, "🎙️ _Listening and processing..._")
        
        async with httpx.AsyncClient() as client:
            # 1. Get File Path from Telegram
            file_info_resp = await client.get(f"{cls.TELEGRAM_API_URL}/getFile?file_id={file_id}")
            file_path = file_info_resp.json().get("result", {}).get("file_path")
            
            if not file_path:
                await cls.send_message(chat_id, "❌ Failed to retrieve audio file.")
                return

            # 2. Download the audio file directly into memory
            audio_url = f"{cls.FILE_API_URL}/{file_path}"
            audio_resp = await client.get(audio_url)
            audio_bytes = audio_resp.content

        # 3. Process via AI
        await cls.process_natural_language(chat_id, audio_bytes=audio_bytes)

    @classmethod
    async def process_natural_language(cls, chat_id: int, text_input: str = None, audio_bytes: bytes = None):
        user_id = cls._get_user_id(chat_id)
        if not user_id:
            await cls.send_message(chat_id, "Please link your account first.")
            return

        try:
            # AI Magic happens here
            parsed_data = AIService.parse_transaction(text_input=text_input, audio_bytes=audio_bytes)
            
            amount = float(parsed_data["amount"])
            tx_type = parsed_data["type"]
            description = parsed_data["description"]
            date = parsed_data["date"] # YYYY-MM-DD

            admin_client = get_supabase_admin()
            
            # Find primary account
            accs = admin_client.table("accounts").select("id, name").eq("user_id", user_id).is_("deleted_at", "null").limit(1).execute()
            if not accs.data:
                await cls.send_message(chat_id, "No active account found. Create one first using `/add_account`.")
                return

            account_id = accs.data[0]["id"]
            acc_name = accs.data[0]["name"]

            # Save to Database
            admin_client.table("transactions").insert({
                "user_id": user_id,
                "account_id": account_id,
                "amount": amount,
                "type": tx_type,
                "description": description,
                "transaction_date": f"{date}T12:00:00Z"
            }).execute()

            symbol = "+" if tx_type == "income" else "-"
            await cls.send_message(
                chat_id,
                f"✨ **Got it!**\n"
                f"• Type: `{tx_type.capitalize()}`\n"
                f"• Amount: `{symbol}₹{amount:,.2f}`\n"
                f"• For: {description}\n"
                f"• Date: {date}\n"
                f"• Account: {acc_name}"
            )

        except Exception as e:
            print(f"AI Parse Error: {str(e)}")
            await cls.send_message(chat_id, "🤖 Sorry, I couldn't understand that transaction. Please try being a bit more specific.")

    @classmethod
    async def send_message(cls, chat_id: int, text: str):
        async with httpx.AsyncClient() as client:
            await client.post(f"{cls.TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

    @classmethod
    def link_chat_id(cls, chat_id: int, code: str):
        admin_client = get_supabase_admin()
        profile = admin_client.table("profiles").select("id").eq("link_code", code).execute()
        if profile.data:
            user_id = profile.data[0]["id"]
            admin_client.table("profiles").update({"telegram_chat_id": chat_id, "link_code": None, "currency": "INR"}).eq("id", user_id).execute()
            accs = admin_client.table("accounts").select("id").eq("user_id", user_id).execute()
            if not accs.data:
                admin_client.table("accounts").insert({"user_id": user_id, "name": "Primary Account", "type": "checking", "balance": 0.0}).execute()
            httpx.post(f"{cls.TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "✅ Account linked successfully!"})
        else:
            httpx.post(f"{cls.TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "❌ Invalid code."})

    @classmethod
    async def handle_balance(cls, chat_id: int):
        user_id = cls._get_user_id(chat_id)
        if not user_id: return
        admin_client = get_supabase_admin()
        accounts = admin_client.table("accounts").select("name, balance, type").eq("user_id", user_id).is_("deleted_at", "null").execute()
        msg = "**Your Account Balances (INR):**\n\n"
        total = 0.0
        for acc in accounts.data:
            bal = float(acc["balance"])
            total += bal
            msg += f"• **{acc['name']}** ({acc['type']}): `₹{bal:,.2f}`\n"
        msg += f"\n**Total Net Worth:** `₹{total:,.2f}`"
        await cls.send_message(chat_id, msg)

    @classmethod
    async def handle_recent(cls, chat_id: int):
        user_id = cls._get_user_id(chat_id)
        if not user_id: return
        admin_client = get_supabase_admin()
        txs = admin_client.table("transactions").select("amount, type, description, transaction_date").eq("user_id", user_id).is_("deleted_at", "null").order("transaction_date", desc=True).limit(5).execute()
        msg = "**Last 5 Transactions:**\n\n"
        for t in txs.data:
            sign = "+" if t["type"] == "income" else "-"
            icon = "🟢" if t["type"] == "income" else "🔴"
            msg += f"{icon} `{sign}₹{float(t['amount']):,.2f}` - {t['description'] or 'Uncategorized'}\n"
        await cls.send_message(chat_id, msg)

    @classmethod
    async def handle_add_account(cls, chat_id: int, text: str):
        user_id = cls._get_user_id(chat_id)
        if not user_id: return
        parts = text.split(" ")
        if len(parts) < 3:
            await cls.send_message(chat_id, "Usage: `/add_account <Name> <Type> [Balance]`")
            return
        admin_client = get_supabase_admin()
        admin_client.table("accounts").insert({"user_id": user_id, "name": parts[1], "type": parts[2].lower(), "balance": float(parts[3]) if len(parts)>3 else 0.0}).execute()
        await cls.send_message(chat_id, f"🎉 Account **{parts[1]}** created.")

    @classmethod
    def _get_user_id(cls, chat_id: int) -> str | None:
        admin_client = get_supabase_admin()
        profile = admin_client.table("profiles").select("id").eq("telegram_chat_id", chat_id).execute()
        if profile.data: return profile.data[0]["id"]
        return None
'''

# ==========================================
# EXECUTION LOGIC
# ==========================================

files_to_write = {
    "requirements.txt": REQUIREMENTS,
    "api/core/config.py": CONFIG_PY,
    "api/services/ai_service.py": AI_SERVICE_PY,
    "api/services/telegram_service.py": TELEGRAM_SERVICE_PY,
}

def main():
    print("Starting PFM codebase update...\n")
    
    for filepath, content in files_to_write.items():
        path = Path(filepath)
        
        # Create directories if they don't exist
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"📁 Created directory: {path.parent}")
            
        # Write the file content
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"✅ Updated file: {filepath}")

    print("\n🎉 Update successful!")
    print("\n--- NEXT STEPS ---")
    print("1. Get a free Gemini API key from: https://aistudio.google.com/app/apikey")
    print("2. Add GEMINI_API_KEY=your_key_here to your local .env file.")
    print("3. Go to Vercel Dashboard -> Settings -> Environment Variables and add GEMINI_API_KEY.")
    print("4. Push your code to Vercel:")
    print("   git add .")
    print('   git commit -m "Added AI natural language and voice parsing"')
    print("   git push")

if __name__ == "__main__":
    main()