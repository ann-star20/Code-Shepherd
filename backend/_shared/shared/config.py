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

    # Internal service-to-service (m1 → api-core)
    api_core_url: str = Field(default="http://api-core:8000")
    internal_service_token: str = Field(default="dev-internal-token")

    # Service URLs
    m0_url: str = Field(default="http://m0:8002")
    m2_url: str = Field(default="http://m2:8003")
    m3_url: str = Field(default="http://m3:8004")
    m4_url: str = Field(default="http://m4:8005")
    m5_url: str = Field(default="http://m5:8006")

    # Neo4j (Module 5 — 로컬 compose 또는 Aura)
    neo4j_uri: str = Field(default="bolt://neo4j:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="codeshepherd")

    # LangSmith (Harness 추적)
    langchain_tracing_v2: bool = Field(default=False)
    langchain_api_key: str = Field(default="")
    langchain_project: str = Field(default="onboarding-platform")

    # LLM — Gemini (팀 통일 모델)
    google_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    use_mock_llm: bool = Field(default=True)
    openai_api_key: str = Field(default="")

    # 임베딩 — Ollama bge-m3
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_embedding_model: str = Field(default="bge-m3")
    ollama_vision_model: str = Field(default="gemma3")
    pgvector_dimension: int = Field(default=1024)
    large_doc_chunk_threshold: int = Field(default=50)

    # Storage — GCS
    storage_backend: str = Field(default="local")   # "gcs" | "local"
    gcs_bucket: str = Field(default="")
    gcs_project: str = Field(default="")

    # 에이전트 실행
    agent_timeout_seconds: int = Field(default=30)

    # KMS 파이프라인 품질 임계값
    markdown_quality_threshold: float = Field(default=0.8)
    gemini_fallback_image_ratio: float = Field(default=0.3)
    upstage_api_key: str = Field(default="")
    upstage_daily_limit: int = Field(default=100)

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
