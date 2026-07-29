import os
import json
from groq import Groq
from api.core.config import settings

class AIService:
    @classmethod
    def get_client(cls):
        api_key = getattr(settings, "GROQ_API_KEY", None) or os.getenv("GROQ_API_KEY", "")
        api_key = str(api_key).strip(" '\"")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing from environment variables.")
        return Groq(api_key=api_key)

    @classmethod
    def parse_transaction(cls, text_input: str = None, audio_bytes: bytes = None) -> dict | list:
        client = cls.get_client()
        content_to_parse = text_input or ""
        
        prompt = f"""
        You are a precise financial data extraction assistant. Analyze the user input and extract financial transaction details.
        The input can be an expense, an income/earning (e.g., "received 10000 extra", "got a bonus of 5000", "earned from freelance"), or a transfer.
        If there are multiple transactions in the input, return a JSON array of objects. If single, return a single JSON object.
        Each object must follow this strict schema:
        {{
            "is_transaction": true/false,
            "description": "Short clear description",
            "amount": 0.00,
            "type": "expense" or "income" or "transfer",
            "category": "Food" or "Extra Income" or "Bonus" or "Salary" or "Freelance" etc.,
            "date": "YYYY-MM-DD"
        }}
        Input: "{content_to_parse}"
        Return ONLY valid JSON.
        """
        
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            raw_text = response.choices[0].message.content.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            return json.loads(raw_text.strip())
        except Exception as e:
            print(f"AI parsing error: {str(e)}")
            return {"is_transaction": False, "description": text_input, "amount": 0.0, "type": "expense", "category": "Miscellaneous"}
