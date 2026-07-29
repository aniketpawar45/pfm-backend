import os
import json
import re
from datetime import datetime, timezone, timedelta
from groq import Groq
from api.core.config import settings

class AIService:
    @classmethod
    def get_groq_client(cls):
        api_key = getattr(settings, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY", "")
        api_key = str(api_key).strip("'\" ")
        if not api_key:
            return None
        return Groq(api_key=api_key)

    @classmethod
    def parse_transaction(cls, text: str) -> dict | list | None:
        client = cls.get_groq_client()
        IST = timezone(timedelta(hours=5, minutes=30))
        today_str = datetime.now(IST).date().isoformat()

        prompt = f"""
You are an AI financial parsing engine for a Telegram PFM bot.
Current Date: {today_str}

Analyze the user's input text and extract financial transaction(s) (expenses, income, or EMI payments).
The user can input single items or a multi-line list of items (e.g., grocery bills).

Return ONLY a valid JSON object or a JSON array of objects with the following keys:
- "is_transaction": boolean (true if it's a financial transaction/list, false otherwise)
- "type": "expense", "income", or "transfer"
- "description": string (name or item description)
- "amount": float (numeric value of the amount)
- "category": string (e.g., Groceries, Food, Utilities, Salary, Miscellaneous, Loans & EMIs)
- "date": string in YYYY-MM-DD format (default to {today_str} if not specified)
- "is_emi_payment": boolean (true if paying off a loan/EMI)
- "lender_name": string or null (if paying EMI, extract the bank or person name)

If the input is a list of multiple items, return a JSON array containing an object for each item.
Do not include any markdown formatting blocks like ```json ... ```, just return raw JSON.

Input text:
"{text}"
"""

        if client:
            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1000
                )
                content = response.choices[0].message.content.strip()
                content = re.sub(r'^```json\s*', '', content, flags=re.IGNORECASE)
                content = re.sub(r'^```\s*', '', content, flags=re.IGNORECASE)
                content = re.sub(r'\s*```$', '', content)
                
                parsed = json.loads(content)
                return parsed
            except Exception as e:
                print(f"Groq API error / Rate limit hit: {str(e)}. Falling back to local Regex parser.")

        # ==========================================
        # LOCAL REGEX FALLBACK PARSER (No AI tokens needed)
        # ==========================================
        lines = text.split('\n')
        results = []
        default_category = "Miscellaneous"
        
        # Check if first line specifies a category
        start_idx = 0
        if len(lines) > 0 and not re.search(r'[₹\d]', lines[0]):
            default_category = lines[0].strip().title()
            start_idx = 1

        for i in range(start_idx, len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            
            # Match amounts like ₹250, 250rs, 250.00, etc.
            amount_match = re.search(r'[₹$]?\s*(\d+(?:\.\d{2})?)', line)
            if amount_match:
                amount_str = amount_match.group(1)
                try:
                    amount = float(amount_str)
                except ValueError:
                    continue
                
                # Extract description by removing the amount part
                desc = re.sub(r'[-–—:]?\s*[₹$]?\s*\d+(?:\.\d{2})?\s*(?:kg|g|ml|l|litre|pcs|piece|bottle)?.*', '', line, flags=re.IGNORECASE).strip()
                desc = re.sub(r'[-–—:]+', '', desc).strip()
                if not desc:
                    desc = "Miscellaneous Item"

                results.append({
                    "is_transaction": True,
                    "type": "expense",
                    "description": desc,
                    "amount": amount,
                    "category": default_category,
                    "date": today_str,
                    "is_emi_payment": False,
                    "lender_name": None
                })

        if results:
            return results if len(results) > 1 else results[0]

        return {"is_transaction": False}
