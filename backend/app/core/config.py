from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Hireonomous"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # MongoDB Settings
    MONGODB_URI: str
    MONGODB_DB: str = "voiceai"

    # OpenAI Settings (for Resume Parsing and optional TTS/STT)
    OPENAI_API_KEY: str
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_STT_MODEL: str = "whisper-1"

    # OpenRouter Settings (for Gemma scoring & classification)
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str = "google/gemma-2-9b-it"
    OPENROUTER_API_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    AI_TIMEOUT: int = 60

    # Hiring Logic
    SHORTLIST_THRESHOLD: int = 70

    # Local Whisper Settings
    WHISPER_MODEL_SIZE: str = "base"  # base, small, medium, large-v3
    WHISPER_DEVICE: str = "cpu"      # cpu or cuda

    # Twilio Settings
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None
    PUBLIC_BASE_URL: Optional[str] = None
    TWILIO_TTS_VOICE: str = "Polly.Joanna"
    TWILIO_RECORDING_DIR: str = "recordings"

    # Vapi Settings
    VAPI_API_KEY: Optional[str] = None
    VAPI_PUBLIC_KEY: Optional[str] = None
    VAPI_AGENT_ID: Optional[str] = None
    VAPI_PHONE_NUMBER_ID: Optional[str] = None

    # Bolna Settings
    BOLNA_API_KEY: Optional[str] = None
    BOLNA_AGENT_ID: Optional[str] = None
    BOLNA_CALLBACK_API_TOKEN: Optional[str] = None

    # Google Drive Settings (for importing resumes from Drive folders)
    GOOGLE_DRIVE_API_KEY: Optional[str] = None

    # AI Interview Settings
    # Public base URL of the candidate-facing frontend, used to build interview links.
    INTERVIEW_PUBLIC_BASE_URL: str = "http://localhost:3000"
    INTERVIEW_TOKEN_TTL_HOURS: int = 72
    INTERVIEW_QUESTION_COUNT: int = 8
    INTERVIEW_MAX_FOLLOWUPS: int = 3
    INTERVIEW_TTS_VOICE: str = "alloy"
    # Optional dedicated secret for hashing interview tokens; falls back to SECRET_KEY env if unset.
    INTERVIEW_TOKEN_SECRET: Optional[str] = None
    # Local media store for interview video/audio recordings (swap for object storage in prod).
    INTERVIEW_MEDIA_DIR: str = "media/interviews"
    INTERVIEW_MEDIA_MAX_MB: int = 200

    # Email Settings
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_USE_TLS: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug(cls, value):
        if isinstance(value, bool) or value is None:
            return value

        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes", "on", "dev", "development", "debug"}:
            return True
        if lowered in {"0", "false", "no", "off", "prod", "production", "release"}:
            return False
        return value

    @field_validator("SMTP_USE_TLS", mode="before")
    @classmethod
    def normalize_smtp_tls(cls, value):
        if isinstance(value, bool) or value is None:
            return value

        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return value

    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

settings = Settings()
