"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = "data/homedoctor.db"
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    APP_VERSION: str = "0.1.0"
    APP_NAME: str = "家庭医生"
    CONFIG_DIR: str = "config/schemas"

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.modelarts-maas.com/openai/v1"
    LLM_MODEL: str = "Kimi-K2.6"
    LLM_FALLBACK_MODELS: str = "GLM-5,qwen3-235b-a22b,DeepSeek-V3"  # comma-separated
    LLM_VISION_BASE_URL: str = "https://api.modelarts-maas.com/v1"
    LLM_VISION_MODEL: str = "qwen2.5-vl-72b"

    # Database encryption (SQLCipher) — empty = no encryption
    DB_ENCRYPTION_KEY: str = ""

    model_config = {"env_prefix": "HOMEDOCTOR_"}


settings = Settings()
