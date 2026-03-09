from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/travelagent"

    # Cache
    redis_url: str = "redis://localhost:6379"

    # Async jobs
    queue_url: str = "http://localhost:4566/000000000000/travel-agent"

    # Storage
    storage_bucket: str = "travel-agent-local"
    storage_endpoint_url: str = "http://localhost:4566"  # LocalStack; empty = real AWS

    # Auth — points to mock-auth in dev, Cognito JWKS in prod
    auth_jwks_url: str = "http://localhost:4000/.well-known/jwks.json"
    auth_audience: str = "travel-agent-local"

    # AI
    anthropic_api_key: str = ""  # Required in prod; validated at agent startup

    # External APIs (sandbox keys for dev, real keys in prod)
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_base_url: str = "https://test.api.amadeus.com"

    openweather_api_key: str = ""
    google_maps_api_key: str = ""
    google_calendar_credentials_json: str = ""  # JSON string of service account creds
    ticketmaster_api_key: str = ""
    opentable_api_key: str = ""
    sherpa_api_key: str = ""
    tripdotcom_api_key: str = ""

    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]

    # SNS (push notifications) — empty disables in dev
    sns_topic_arn: str = ""

    # API docs — set to False in production
    docs_enabled: bool = True

    # Rate limits (requests per minute per user, external-facing endpoints only)
    rate_limit_read_per_minute: int = 60
    rate_limit_write_per_minute: int = 30
    rate_limit_chat_per_minute: int = 10

    # Agent safety
    agent_max_iterations: int = 10
    chat_message_max_length: int = 4000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
