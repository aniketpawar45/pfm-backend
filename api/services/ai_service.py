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
    def get_financial_advice(cls, chat_id: int, user_query: str) -> str:
        from api.services.db_service import DBService
        client = cls.get_groq_client()
        if not client:
            return "⚠️ AI Advisory is offline. GROQ_API_KEY is missing."

        try:
            # Fetch real-time data to ground the AI's advice
            context = DBService.get_financial_context(chat_id)
            
            loans_str = ", ".join([f"{l['name']} (Rem: ₹{l['remaining_amount']:,.0f})" for l in context['loans']]) or "None"
            subs_str = ", ".join([f"{s['name']} (₹{s['amount']:,.0f})" for s in context['subs']]) or "None"
            
            prompt = f"""
You are a top-tier financial advisor for a Telegram Personal Finance bot. 
The user is asking for financial advice: "{user_query}"

Here is their EXACT current financial context:
- Monthly Net Salary: ₹{context['budget']['base_salary']:,.2f}
- Monthly Safe House Budget (after EMIs): ₹{context['budget']['safe_house_budget']:,.2f}
- Actual Spent This Month: ₹{context['budget']['actual_house_spent']:,.2f} ({context['budget']['percentage_used']}% utilized)
- Active Loans: {loans_str}
- Active Subscriptions: {subs_str}
- Average Daily Spend: ₹{context['stats']['avg_daily_spend']:,.2f}
- Savings Rate: {context['stats']['savings_rate']:.1f}%

Provide concise, highly practical, and personalized financial advice based on this exact data. Keep it under 150 words. Be direct, authoritative, and helpful. Use standard Markdown for formatting. Do not use generic pleasantries.
            """
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=300
            )
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"AI Advisory Error: {str(e)}")
            return "⚠️ Sorry, I encountered an issue generating your financial advice. Please try again later."

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
- "category": string (e.g., Groceries, Food, Utilities, Salary, Miscellaneous, Subscriptions, Loans & EMIs)
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

        # LOCAL REGEX FALLBACK
        lines = text.split('\n')
        results = []
        default_category = "Miscellaneous"
        
        start_idx = 0
        if len(lines) > 0 and not re.search(r'[₹\d]', lines[0]):
            default_category = lines[0].strip().title()
            start_idx = 1

        for i in range(start_idx, len(lines)):
            line = lines[i].strip()
            if not line: continue
            amount_match = re.search(r'[₹$]?\s*(\d+(?:\.\d{2})?)', line)
            if amount_match:
                try: amount = float(amount_match.group(1))
                except ValueError: continue
                desc = re.sub(r'[-–—:]?\s*[₹$]?\s*\d+(?:\.\d{2})?\s*(?:kg|g|ml|l|litre|pcs|piece|bottle)?.*', '', line, flags=re.IGNORECASE).strip()
                desc = re.sub(r'[-–—:]+', '', desc).strip() or "Miscellaneous Item"

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
