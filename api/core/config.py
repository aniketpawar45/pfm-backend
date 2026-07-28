from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    TELEGRAM_BOT_TOKEN: str
    JWT_SECRET: str
    GEMINI_API_KEY: str
    ENVIRONMENT: str = "production"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
