import secrets
from fastapi import APIRouter, Depends
from api.core.security import get_current_user_id
from api.core.database import get_supabase_admin

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/telegram-link")
def get_link_code(user_id: str = Depends(get_current_user_id)):
    code = secrets.token_hex(16)
    get_supabase_admin().table("profiles").update({"link_code": code}).eq("id", user_id).execute()
    return {"instruction": f"Send `/link {code}` to your Telegram bot."}
