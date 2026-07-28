from typing import List, Dict, Any
from datetime import datetime
from api.core.database import get_supabase_user_client
from api.models.schemas import AccountCreate, TransactionCreate

class FinancialService:
    @staticmethod
    def create_account(user_id: str, token: str, data: AccountCreate) -> Dict[str, Any]:
        client = get_supabase_user_client(token)
        payload = data.model_dump()
        payload["user_id"] = user_id
        payload["balance"] = float(data.balance)
        return client.table("accounts").insert(payload).execute().data[0]

    @staticmethod
    def create_transaction(user_id: str, token: str, data: TransactionCreate) -> Dict[str, Any]:
        client = get_supabase_user_client(token)
        payload = data.model_dump()
        payload["user_id"] = user_id
        payload["amount"] = float(data.amount)
        payload["transaction_date"] = data.transaction_date.isoformat()
        return client.table("transactions").insert(payload).execute().data[0]
