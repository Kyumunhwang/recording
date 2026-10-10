"""Configuration module for Meeting Summary Backend."""
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment or defaults."""
    APP_NAME: str = "Counseling Meeting Summary System"
    DEBUG: bool = True
    PORT: int = 3850
    HOST: str = "127.0.0.1"

    # Directory Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    SESSIONS_DIR: Path = STORAGE_DIR / "sessions"
    RECORDINGS_DIR: Path = STORAGE_DIR / "recordings"

    # API Keys & Endpoints (Optional for Mock/Local mode)
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GAS_WEBHOOK_URL: str = ""  # Google Apps Script Webhook URL

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
settings.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
settings.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
