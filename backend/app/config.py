"""Application configuration via pydantic-settings.

Secret resolution for ``LLM_API_KEY`` (and other sensitive values) follows
the priority chain defined in :mod:`app.secrets`:

    env var → OS keyring → local file → default

This keeps Docker deployments (env var) working unchanged while enabling
OS-native keychain storage on local developer machines (spec §12.1 P0).
"""

from pydantic_settings import BaseSettings

from app.secrets import get_secret


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = "data/homedoctor.db"
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    APP_VERSION: str = "0.1.0"
    APP_NAME: str = "家庭医生"
    CONFIG_DIR: str = "config/schemas"

    # When False, the OS keyring is never consulted for secret resolution.
    KEYRING_ENABLED: bool = True

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.modelarts-maas.com/openai/v1"
    LLM_MODEL: str = "Kimi-K2.6"
    LLM_FALLBACK_MODELS: str = "GLM-5,qwen3-235b-a22b,DeepSeek-V3"  # comma-separated
    LLM_VISION_BASE_URL: str = "https://api.modelarts-maas.com/v1"
    LLM_VISION_MODEL: str = "qwen2.5-vl-72b"

    # Database encryption (SQLCipher) — empty = no encryption
    DB_ENCRYPTION_KEY: str = ""

    model_config = {"env_prefix": "HOMEDOCTOR_"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # If LLM_API_KEY was not provided via env (Docker path), resolve it
        # through the secret chain: keyring → file. The env var is already
        # checked inside get_secret(), so this is a no-op when it is set.
        if not self.LLM_API_KEY:
            self.LLM_API_KEY = get_secret(
                "llm_api_key",
                "HOMEDOCTOR_LLM_API_KEY",
                use_keyring=self.KEYRING_ENABLED,
            )


settings = Settings()
