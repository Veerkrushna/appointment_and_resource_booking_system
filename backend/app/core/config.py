from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Appointment & Resource Booking System created by Namit & Nikhil"
    environment: str = "development"
    debug: bool = True
    database_url: str
    cancellation_grace_period_minutes: int = 60

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_from: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_phone: str | None = None

    redis_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    feedback_delay_minutes: int = 15
    auth_secret: str = "change-this-secret-in-production"
    auth_token_expiry_seconds: int = 60 * 60 * 24 * 7

    razorpay_key_id: str = "rzp_test_1234567890abcdef"
    razorpay_key_secret: str = "rzp_test_secret_placeholder"
    razorpay_webhook_secret: str = "rzp_test_webhook_secret_placeholder"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
