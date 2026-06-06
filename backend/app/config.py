"""Typed application settings, loaded from environment / .env.

All knobs in one place. Defaults are safe for import (so tests and the smoke
suite never crash on a missing var); real values come from `.env` (see
`.env.example`). Secrets stay in the environment, never in code.
"""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the .env at the repo root regardless of the working directory the
# backend is launched from (README runs `cd backend && uvicorn ...`, so a bare
# ".env" would be looked up under backend/ and silently miss the real file).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # Phoenix ERP
    PHOENIX_API_BASE_URL: str = "http://localhost:8000"
    PHOENIX_API_TOKEN: str = ""

    # SSH access to customer VMs.
    # Single-key mode: point SSH_PRIVATE_KEY_PATH at one .pem. Per-VM mode: leave it
    # unset/missing and drop caseN_key.pem files in SSH_KEY_DIR (N = ticket_id - 7000).
    SSH_PRIVATE_KEY_PATH: str = "/keys/key.pem"
    SSH_KEY_DIR: str = "/keys"
    SSH_USERNAME: str = "azureuser"
    SSH_KEY_PASSPHRASE: Optional[str] = None

    # Azure OpenAI credentials (used by the azure-openai provider — ADR-0010, was ADR-0006)
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"  # unused on the v1 Foundry path; kept for reference

    # LLM (ADR-0010) — model-agnostic provider selection via LangChain.
    LLM_PROVIDER: str = "azure-openai"
    LLM_MODEL: str = ""  # empty -> falls back to AZURE_OPENAI_DEPLOYMENT for azure
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Timeouts & guardrails
    HTTP_TIMEOUT_SECONDS: float = 15.0
    HTTP_RETRIES: int = 2
    SSH_CONNECT_TIMEOUT: float = 15.0
    SSH_COMMAND_TIMEOUT: float = 60.0
    AGENT_MAX_STEPS: int = 25

    # Memory (ADR-0001) + audit (ADR-0008)
    MEMORY_DIR: str = "backend/memory"
    AUDIT_DIR: str = "data/audit"


settings = Settings()
