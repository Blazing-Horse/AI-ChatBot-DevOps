"""Reads all settings from environment variables, in one place."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    use_fakes: bool
    openai_base_url: str
    model_deployment: str
    cosmos_endpoint: str
    cosmos_database: str
    cosmos_container: str
    allowed_origins: list[str]
    appinsights_connection_string: str
    history_limit: int = 10
    max_message_length: int = 2000


def load_settings() -> Settings:
    origins = os.getenv("ALLOWED_ORIGINS", "")
    return Settings(
        use_fakes=os.getenv("USE_FAKES", "false").lower() == "true",
        openai_base_url=os.getenv("AZURE_OPENAI_BASE_URL", ""),
        model_deployment=os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-5-nano"),
        cosmos_endpoint=os.getenv("COSMOS_ENDPOINT", ""),
        cosmos_database=os.getenv("COSMOS_DATABASE", "chatbot"),
        cosmos_container=os.getenv("COSMOS_CONTAINER", "messages"),
        allowed_origins=[o.strip() for o in origins.split(",") if o.strip()],
        appinsights_connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", ""),
    )
