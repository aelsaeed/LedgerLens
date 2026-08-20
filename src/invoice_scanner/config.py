"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEDGERLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ocr_lang: str = "eng"
    ocr_timeout_seconds: int = Field(default=15, gt=0, le=120)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=25_000_000, gt=0)
    expose_raw_text: bool = True


@lru_cache
def get_settings() -> Settings:
    """Build settings once while keeping tests able to inject their own instance."""

    return Settings()
