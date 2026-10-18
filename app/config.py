from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    opensearch_url: str = "http://localhost:9200"
    # If set, POST /webhooks/datadog requires a matching X-Webhook-Token header.
    webhook_token: str = ""


settings = Settings()
