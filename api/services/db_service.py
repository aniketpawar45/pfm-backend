from datetime import datetime
from supabase import create_client
from api.core.config import settings

class DBService:
    @classmethod
    def get_client(cls):
        url = settings.SUPABASE_URL.strip("'\" ")
        key = settings.SUPABASE_KEY.strip("'\" ")
        return create_client(url, key)

    @classmethod
    def save_transactions(cls, chat_id: int, parsed_data: dict | list) -> int:
        supabase = cls.get_client()
        
        items = parsed_data if isinstance(parsed_data, list) else [parsed_data]
        
        valid_records = []
        for item in items:
            if not item.get("is_transaction", True) or item.get("amount") is None:
                continue
                
            valid_records.append({
                "chat_id": chat_id,
                "description": item.get("description") or "Miscellaneous",
                "amount": float(item.get("amount")),
                "type": item.get("type", "expense"),
                "category": item.get("category") or "Miscellaneous",
                "date": item.get("date") or datetime.now().date().isoformat()
            })
            
        if not valid_records:
            return 0

        supabase.table("transactions").insert(valid_records).execute()
        return len(valid_records)