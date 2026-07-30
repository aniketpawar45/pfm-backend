import os
import base64
import json
from fastapi import APIRouter, Request
import httpx
from groq import Groq
from supabase import create_client, Client

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ALLOWED_IDS = [int(x.strip()) for x in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",") if x.strip()]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

@router.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        
        if "message" not in data:
            return {"status": "ignored"}
        
        message = data["message"]
        chat_id = message["chat"]["id"]

        # Security check: restrict access to allowed Telegram IDs
        if ALLOWED_IDS and chat_id not in ALLOWED_IDS:
            await send_telegram_message(chat_id, "Unauthorized access.")
            return {"status": "unauthorized"}

        # 1. Handle Receipt Photo Uploads
        if "photo" in message:
            # Grab the highest-resolution photo (last in the array)
            photo = message["photo"][-1]
            file_id = photo["file_id"]
            
            async with httpx.AsyncClient() as client:
                # Fetch file path from Telegram API
                file_path_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
                res = await client.get(file_path_url)
                file_info = res.json()
                
                if not file_info.get("ok"):
                    await send_telegram_message(chat_id, "Failed to retrieve receipt image details.")
                    return {"status": "error"}
                
                file_path = file_info["result"]["file_path"]
                
                # Download binary image bytes from Telegram servers
                download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                img_res = await client.get(download_url)
                img_bytes = img_res.content
            
            # Convert binary bytes to Base64 data URI
            base64_image = base64.b64encode(img_bytes).decode("utf-8")
            data_uri = f"data:image/jpeg;base64,{base64_image}"
            
            # Parse receipt using Groq Vision AI
            parsed = parse_receipt_with_ai(data_uri)
            
            if parsed and "amount" in parsed:
                supabase.table("transactions").insert({
                    "chat_id": chat_id,
                    "amount": parsed["amount"],
                    "category": parsed.get("category", "Shopping"),
                    "description": parsed.get("description", "Scanned Receipt")
                }).execute()
                
                await send_telegram_message(
                    chat_id, 
                    f"Receipt Scanned & Saved!\n"
                    f"Amount: ${parsed['amount']}\n"
                    f"Category: {parsed.get('category', 'Shopping')}\n"
                    f"Merchant/Desc: {parsed.get('description', 'N/A')}"
                )
            else:
                await send_telegram_message(chat_id, "Could not extract data from this receipt. Please ensure it is clear.")
            
            return {"status": "ok"}

        # 2. Handle Text Messages & Commands
        text = message.get("text", "")
        
        if text.startswith("/start"):
            await send_telegram_message(
                chat_id, 
                "Welcome to your PFM Bot!\n\n"
                "• Send text like: 'Spent $25 on groceries'\n"
                "• Upload receipt photos for automatic scanning\n"
                "• Use /summary to check spending"
            )
        elif text.startswith("/summary"):
            summary_text = get_user_summary(chat_id)
            await send_telegram_message(chat_id, summary_text)
        else:
            # Parse natural language text expense via Groq AI
            parsed = parse_expense_with_ai(text)
            if parsed and "amount" in parsed:
                supabase.table("transactions").insert({
                    "chat_id": chat_id,
                    "amount": parsed["amount"],
                    "category": parsed.get("category", "General"),
                    "description": parsed.get("description", text)
                }).execute()
                await send_telegram_message(
                    chat_id, 
                    f"Recorded: ${parsed['amount']} for {parsed.get('category', 'General')}"
                )
            else:
                await send_telegram_message(
                    chat_id, 
                    "Could not parse expense. Try something like: 'Spent $20 on coffee' or upload a receipt photo."
                )

        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error", "detail": str(e)}

def parse_receipt_with_ai(data_uri: str) -> dict:
    prompt = (
        "Analyze this receipt image. Extract the total amount (as a float), "
        "category (e.g., Food, Groceries, Transport, Shopping), and merchant name "
        "or description (as a string). Return strictly as JSON with keys: amount, category, description."
    )
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}}
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"Vision AI error: {e}")
        return {}

def parse_expense_with_ai(text: str) -> dict:
    prompt = f"Extract amount (float), category (string), and description (string) from this text: '{text}'. Return strictly as JSON with keys: amount, category, description."
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception:
        return {}

def get_user_summary(chat_id: int) -> str:
    res = supabase.table("transactions").select("amount, category").eq("chat_id", chat_id).execute()
    if not res.data:
        return "No transactions recorded yet."
    total = sum(item["amount"] for item in res.data)
    return f"Total Spending: ${total:.2f}\nTotal Transactions: {len(res.data)}"

async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})
