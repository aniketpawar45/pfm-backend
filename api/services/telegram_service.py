import json
import os
from datetime import datetime, timezone, timedelta
from openai import OpenAI
from api.core.config import settings

class AIService:
    @classmethod
    def parse_transaction(cls, text_input: str = None, audio_bytes: bytes = None) -> dict | list:
        # Forcefully purge any rogue or empty environment variables that break httpx
        for env_var in ["OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_KEY"]:
            os.environ.pop(env_var, None)

        api_key = settings.GROQ_API_KEY.strip("'\" ") if settings.GROQ_API_KEY else ""
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing or empty.")

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        
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
            f"1. LISTS/BREAKDOWNS: If the user provides an itemized list or grocery list, aggregate them into a SINGLE bulk expense transaction. If a grand total is provided at the bottom, use it. If NO grand total is provided, you MUST carefully calculate the exact mathematical sum of all individual item prices step-by-step to ensure 100% numerical accuracy.\n"
            f"2. MULTI-ACTIONS: If multiple distinct transactions are described, return a JSON array of transaction objects. If a single transaction, return a single JSON object.\n"
            f"3. Each transaction object must contain strictly these keys:\n"
            f"   - is_transaction: boolean (true if financial, false if general chat/non-financial)\n"
            f"   - amount: float or null (numeric value only, exact calculated sum, no currency symbols)\n"
            f"   - type: string ('expense' or 'income') or null\n"
            f"   - description: string or null (short, clean description like 'Monthly Groceries')\n"
            f"   - date: string or null (YYYY-MM-DD format, infer relative dates based on IST date)\n"
            f"Return ONLY valid JSON with no markdown wrapping if possible."
        )

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": text_input or ""}
                ],
                temperature=0.0  # Set temperature to 0 for maximum mathematical determinism
            )
        except Exception as e:
            raise ValueError(f"Groq API call failed: {str(e)}")
        
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