from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str = "mistral/mistral-small-latest"
    ALLOWED_ORIGINS: str = "https://austr.ai,https://www.austr.ai,http://localhost:4321"
    RATE_LIMIT_PER_IP: int = 20
    RATE_LIMIT_GLOBAL: int = 200
    MIN_REQUEST_DELAY: float = 1.0
    MAX_TEXT_LENGTH: int = 2000
    SESSION_TTL: int = 1800
    CONFIDENCE_THRESHOLD: float = 0.6

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
