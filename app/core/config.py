from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Photobooth Backend"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "15432"
    POSTGRES_USER: str = "photobooth"
    POSTGRES_PASSWORD: str = "photobooth_secure_pass"
    POSTGRES_DB: str = "photobooth_db"

    # Payment Gateway Configuration (PayOS / VietQR)
    PAYOS_CLIENT_ID: str = "fake-payos-client-id"
    PAYOS_API_KEY: str = "fake-payos-api-key"
    PAYOS_CHECKSUM_KEY: str = "fake_payos_checksum_key_for_testing"
    ORDER_PAYMENT_TIMEOUT_MINUTES: int = 15

    # Dedicated database used ONLY by the test suite (tests drop/create all tables).
    # Defaults to "<POSTGRES_DB>_test" on the same server when unset.
    TEST_DATABASE_URL: str | None = None

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


settings = Settings()
