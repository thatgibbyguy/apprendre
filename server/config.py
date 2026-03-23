"""Application configuration."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """Application settings."""

    app_name: str = "Apprendre"
    debug: bool = True
    database_path: str = "apprendre.db"
    static_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "static")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "phi3:14b"
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
