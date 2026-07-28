import json
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from api.core.config import settings


class AIService:
    @classmethod
    def parse_transaction(cls, text_input: str = None, audio_bytes: bytes = None) -> dict:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        contents = []

        IST = timezone(timedelta(hours=5, minutes=30))
        current_date_ist = datetime.now(IST).date().isoformat()

        system_instruction = (
            f"You are an AI financial assistant that parses natural language or audio into financial transactions in Indian Rupees (INR).\n"
            f"Today's date in IST is {current_date_ist}.\n"
            f"Analyze the input text or audio. Determine if it describes a financial transaction (income or expense).\n"
            f"Return strict JSON with these keys:\n"
            f"- is_transaction: boolean (true if it's a financial transaction, false if it's general chat, weather, greetings, or non-financial questions)\n"
            f"- amount: float or null (numeric value only, no currency symbols)\n"
            f"- type: string ('expense' or 'income') or null\n"
            f"- description: string or null (short, clean description)\n"
            f"- date: string or null (YYYY-MM-DD format, infer relative dates like 'yesterday' or 'today' based on IST date)\n"
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