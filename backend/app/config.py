"""Typed application settings loaded from the environment.

Defaults keep imports and tests safe. Real secrets come from `.env` or the
process environment and should never be written into the codebase.
"""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load the repo-root .env, even when the backend is started from backend/.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """All runtime knobs for Phoenix, SSH, Azure, and safety timeouts."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # Phoenix ERP mock connection.
    PHOENIX_API_BASE_URL: str = "http://localhost:8000"
    PHOENIX_API_TOKEN: str = ""

    # SSH access to customer VMs. Use one shared key, or per-ticket caseN_key.pem files.
    SSH_PRIVATE_KEY_PATH: str = "/keys/key.pem"
    SSH_KEY_DIR: str = "/keys"
    SSH_USERNAME: str = "azureuser"
    SSH_KEY_PASSPHRASE: Optional[str] = None

    # Azure OpenAI settings. Empty values make the agent use safe fallback diagnostics.
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"

    # Timeouts and guardrails keep external calls from hanging the demo.
    HTTP_TIMEOUT_SECONDS: float = 15.0
    HTTP_RETRIES: int = 2
    SSH_CONNECT_TIMEOUT: float = 15.0
    SSH_COMMAND_TIMEOUT: float = 60.0
    AGENT_MAX_STEPS: int = 25

    # Local folders for future memory notes and persisted audit logs.
    MEMORY_DIR: str = "backend/memory"
    AUDIT_DIR: str = "data/audit"


settings = Settings()
