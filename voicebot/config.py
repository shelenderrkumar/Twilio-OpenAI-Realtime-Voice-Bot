"""Runtime configuration, loaded from environment variables (or a `.env` file)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- OpenAI Realtime -------------------------------------------------
    openai_api_key: SecretStr = SecretStr("")
    realtime_model: str = "gpt-4o-realtime-preview"
    realtime_url: str = "wss://api.openai.com/v1/realtime"
    voice: str = "alloy"
    embedding_model: str = "text-embedding-3-small"

    # --- Agent -----------------------------------------------------------
    agent_profile: Literal["logistics", "grocery"] = "logistics"
    # Older conversation items are pruned server-side to bound latency and cost.
    max_conversation_items: int = Field(default=4, ge=1)

    # --- Server / Twilio -------------------------------------------------
    port: int = 5050
    # Public hostname Twilio should stream audio to (e.g. your ngrok domain).
    # Falls back to the Host header of the incoming webhook.
    public_host: str | None = None
    # When set, incoming Twilio webhooks must carry a valid X-Twilio-Signature.
    twilio_auth_token: SecretStr | None = None

    # --- Data & integrations ---------------------------------------------
    knowledge_base_dir: Path = DATA_DIR / "knowledge_base"
    knowledge_index_dir: Path = DATA_DIR / "indexes" / "knowledge_base"
    catalog_csv: Path = DATA_DIR / "grocery_catalog.csv"
    catalog_index_dir: Path = DATA_DIR / "indexes" / "grocery_catalog"
    orders_csv: Path = DATA_DIR / "orders.csv"
    # Optional external shipment-tracking API; the local orders file is used when unset.
    tracking_api_url: str | None = None
    tavily_api_key: SecretStr | None = None

    # Complaint e-mails go to Gmail when OAuth files exist, otherwise they are logged.
    gmail_credentials_file: Path = PROJECT_ROOT / "secrets" / "credentials.json"
    gmail_token_file: Path = PROJECT_ROOT / "secrets" / "token.json"
    support_email: str = "support@example.com"
    complaint_sender: str = "voicebot@example.com"
    complaint_cc: list[str] = Field(default_factory=list)

    @field_validator(
        "public_host", "twilio_auth_token", "tracking_api_url", "tavily_api_key", mode="before"
    )
    @classmethod
    def _blank_is_unset(cls, value):
        # `FOO=` in a .env file means "not configured", not "configured as empty".
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
