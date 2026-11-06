from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "development-only-change-me"
    database_url: str | None = None
    storage_dir: Path = Path("./uploads")
    access_token_minutes: int = 60
    firebase_project_id: str | None = None
    firebase_api_key: str | None = None
    firebase_auth_domain: str | None = None
    firebase_app_id: str | None = None
    free_credits: int = 5
    credit_cost_per_generation: int = 1
    max_upload_mb: int = 25
    transcription_api_url: str | None = None
    transcription_api_key: str | None = None

    mpesa_base_url: str = "https://sandbox.safaricom.co.ke"
    mpesa_consumer_key: str | None = None
    mpesa_consumer_secret: str | None = None
    mpesa_shortcode: str | None = None
    mpesa_passkey: str | None = None
    mpesa_callback_url: str | None = None
    mpesa_callback_token: str | None = None
    mpesa_paybill_or_till: str | None = None
    mpesa_payment_type: Literal["paybill", "till"] = "paybill"

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    payment_success_url: str = "http://localhost:8000/payment/success"
    payment_cancel_url: str = "http://localhost:8000/payment/cancel"

    whisper_model_id: str | None = None
    nematron_model_id: str | None = None

    pynnote_api_key: str | None = None
    pynnote_api_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_limits(self) -> "Settings":
        if self.access_token_minutes < 1:
            raise ValueError("ACCESS_TOKEN_MINUTES must be positive.")
        if self.free_credits < 0 or self.credit_cost_per_generation < 0:
            raise ValueError("Credit settings cannot be negative.")
        if self.max_upload_mb < 1:
            raise ValueError("MAX_UPLOAD_MB must be positive.")
        if self.app_env.lower() == "production" and (
            self.secret_key == "development-only-change-me"
            or len(self.secret_key.encode()) < 32
        ):
            raise ValueError("Production SECRET_KEY must contain at least 32 bytes.")
        if (
            self.app_env.lower() == "production"
            and self.mpesa_callback_token
            and len(self.mpesa_callback_token) < 32
        ):
            raise ValueError("Production MPESA_CALLBACK_TOKEN must contain at least 32 characters.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
