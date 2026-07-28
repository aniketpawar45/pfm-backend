from supabase import create_client, Client
from api.core.config import settings

def get_supabase_admin() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

def get_supabase_user_client(token: str) -> Client:
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    client.postgrest.auth(token)
    return client
