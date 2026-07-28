import json
from datetime import datetime
import pytz
from google import genai
from google.genai import types
from api.core.config import settings

class AIService:
    @staticmethod
    def parse_transaction(text_input: str = None, audio_bytes: bytes = None) -> dict:
        # Lazy initialization: Only boots up when a message is received
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
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
            contents.append(
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg")
            )
        elif text_input:
            contents.append(f"User input: {text_input}")
        else:
            raise ValueError("Must provide text or audio")

        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

        try:
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            raise ValueError(f"Failed to parse AI response: {str(e)}")
