import json
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from api.core.config import settings


class AIService:
    @classmethod
    def parse_transaction(cls, text_input: str = None, audio_bytes: bytes = None) -> dict | list:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        contents = []

        IST = timezone(timedelta(hours=5, minutes=30))
        current_date_ist = datetime.now(IST).date().isoformat()

        system_instruction = (
            f"You are an AI financial assistant that parses natural language, audio, or itemized lists into financial transactions in Indian Rupees (INR).\n"
            f"Today's date in IST is {current_date_ist}.\n"
            f"CRITICAL RULE FOR LISTS/BREAKDOWNS: If the user provides a large itemized list, budget breakdown, or grocery list, do NOT create individual transactions for every single item. Instead, aggregate them into a SINGLE bulk expense transaction using the grand total or estimated total provided at the bottom (or sum the items if needed), with a clean description like 'Monthly Groceries'.\n"
            f"For normal multi-action sentences (e.g., 'took 500 from X and gave 200 to Y'), return a JSON array of separate transaction objects. For a single transaction, return a single JSON object.\n"
            f"Each transaction object must have these keys:\n"
            f"- is_transaction: boolean (true if it's a financial transaction, false if general chat or non-financial)\n"
            f"- amount: float or null (numeric value only, no currency symbols)\n"
            f"- type: string ('expense' or 'income') or null\n"
            f"- description: string or null (short, clean description)\n"
            f"- date: string or null (YYYY-MM-DD format, infer relative dates based on IST date)\n"
        )

        if audio_bytes:
            contents.append(
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/ogg",
                )
            )

        if text_input:
            contents.append(text_input)

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            ),
        )

        try:
            result_text = response.text
            data = json.loads(result_text)
            return data
        except Exception as e:
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")