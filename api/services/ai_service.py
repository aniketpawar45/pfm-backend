import json
from datetime import datetime, timezone, timedelta
from openai import OpenAI
from api.core.config import settings


class AIService:
    @classmethod
    def parse_transaction(cls, text_input: str = None, audio_bytes: bytes = None) -> dict | list:
        # Initialize Groq client using its OpenAI-compatible high-speed endpoint
        client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

        # Transcribe voice notes securely in-memory using Whisper Large V3
        if audio_bytes:
            try:
                audio_file = ("voice_note.ogg", audio_bytes)
                transcript = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=audio_file,
                    response_format="text"
                )
                text_input = transcript
            except Exception as e:
                raise ValueError(f"Failed to transcribe audio: {str(e)}")

        IST = timezone(timedelta(hours=5, minutes=30))
        current_date_ist = datetime.now(IST).date().isoformat()

        system_instruction = (
            f"You are an AI financial assistant that parses natural language, itemized lists, or text into financial transactions in Indian Rupees (INR).\n"
            f"Today's date in IST is {current_date_ist}.\n"
            f"CRITICAL RULES:\n"
            f"1. LISTS/BREAKDOWNS: If the user provides a large itemized list or grocery list, aggregate them into a SINGLE bulk expense transaction using the grand total or estimated total provided at the bottom, with a clean description like 'Monthly Groceries'.\n"
            f"2. MULTI-ACTIONS: If multiple distinct transactions are described (e.g., 'took 500 from X and gave 200 to Y'), return a JSON array of transaction objects. If a single transaction, return a single JSON object.\n"
            f"3. Each transaction object must contain strictly these keys:\n"
            f"   - is_transaction: boolean (true if financial, false if general chat/non-financial)\n"
            f"   - amount: float or null (numeric value only, no currency symbols)\n"
            f"   - type: string ('expense' or 'income') or null\n"
            f"   - description: string or null (short, clean description)\n"
            f"   - date: string or null (YYYY-MM-DD format, infer relative dates based on IST date)\n"
            f"Return ONLY valid JSON with no markdown wrapping if possible."
        )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": text_input or ""}
            ],
            temperature=0.1
        )

        try:
            result_text = response.choices[0].message.content.strip()
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]

            data = json.loads(result_text.strip())
            return data
        except Exception as e:
            raise ValueError(f"Failed to parse AI response as JSON: {str(e)}")