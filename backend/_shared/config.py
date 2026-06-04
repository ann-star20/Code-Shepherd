"""pydantic-settings 기반 설정 로더 — 모든 서비스가 이 모듈을 통해 환경 변수 로드."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # DB (Cloud SQL via Auth Proxy)
    db_host: str = Field(default="cloud-sql-proxy")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="")
    db_user: str = Field(default="")
    db_password: str = Field(default="")
    test_db_name: str = Field(default="codeshepherd_test")

    # Cloud SQL Auth Proxy
    cloudsql_instance_connection_name: str = Field(default="")
    google_application_credentials: str = Field(default="/secrets/sa-key.json")

    # Auth
    jwt_secret: str = Field(default="dev-secret-change-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)
    jwt_refresh_token_expire_days: int = Field(default=30)
    github_oauth_client_id: str = Field(default="")
    github_oauth_client_secret: str = Field(default="")
    github_oauth_redirect_uri: str = Field(
        default="http://localhost:5173/auth/callback"
    )

    # Orchestrator
    github_webhook_secret: str = Field(default="")

    # Service URLs
    m0_url: str = Field(default="http://m0:8002")
    m2_url: str = Field(default="http://m2:8003")
    m3_url: str = Field(default="http://m3:8004")
    m4_url: str = Field(default="http://m4:8005")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def test_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.test_db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
