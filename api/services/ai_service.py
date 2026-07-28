import json
from datetime import date
from google import genai
from google.genai import types
from api.core.config import settings


class AIService:
    @classmethod
    def parse_transaction(cls, text_input: str = None, audio_bytes: bytes = None) -> dict:
        # Initialize the modern Google GenAI client
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        contents = []

        system_instruction = (
            f"You are an AI financial assistant that parses natural language or audio into financial transactions in Indian Rupees (INR).\n"
            f"Today's date is {date.today().isoformat()}.\n"
            f"Extract the following fields and return them in strict JSON format:\n"
            f"- amount: float (numeric value only, no currency symbols)\n"
            f"- type: string ('expense' or 'income')\n"
            f"- description: string (short, clean description of the transaction)\n"
            f"- date: string (YYYY-MM-DD format, infer relative dates like 'yesterday' or 'today' based on the current date)\n"
        )

        # Handle audio bytes if a voice note was sent
        if audio_bytes:
            contents.append(
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/ogg",
                )
            )

        # Handle text input if available
        if text_input:
            contents.append(text_input)

        # Call the model using the correct name WITHOUT the 'models/' prefix
        response = client.models.generate_content(
            model="gemini-1.5-flash",
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