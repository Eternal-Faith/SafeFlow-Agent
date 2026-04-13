from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class Settings(BaseModel):
    app_name: str = "SafeFlow-Agent"
    llm_model: str = Field(default_factory=lambda: os.getenv("SAFEFLOW_LLM_MODEL", "gpt-4o-mini"))
    vision_model: str = Field(default_factory=lambda: os.getenv("SAFEFLOW_VISION_MODEL", os.getenv("SAFEFLOW_LLM_MODEL", "gpt-4o-mini")))
    audio_model: str = Field(default_factory=lambda: os.getenv("SAFEFLOW_AUDIO_MODEL", os.getenv("SAFEFLOW_LLM_MODEL", "gpt-4o-mini")))
    openai_api_key: str | None = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_base_url: str | None = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
    db_path: Path = Field(
        default_factory=lambda: Path(os.getenv("SAFEFLOW_DB_PATH", "var/safeflow_runs.sqlite3"))
    )
    chroma_dir: Path = Field(default_factory=lambda: Path(os.getenv("SAFEFLOW_CHROMA_DIR", "var/chroma")))
    max_clarification_rounds: int = 2
    top_k_retrieval: int = 4

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    def ensure_runtime_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
