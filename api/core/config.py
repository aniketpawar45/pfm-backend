from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    TELEGRAM_BOT_TOKEN: str
    GROQ_API_KEY: str

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()