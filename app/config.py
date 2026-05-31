from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Mac Daily Intelligence")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/mac_daily.db")
    report_dir: Path = ROOT_DIR / os.getenv("REPORT_DIR", "reports")
    sample_data_path: Path = ROOT_DIR / os.getenv("SAMPLE_DATA_PATH", "data/sample_sources.json")
    client_profile_path: Path = ROOT_DIR / os.getenv("CLIENT_PROFILE_PATH", "data/client_profile.json")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    cron_secret: str = os.getenv("CRON_SECRET", "")
    x_bearer_token: str = os.getenv("X_BEARER_TOKEN", "")
    tiktok_api_key: str = os.getenv("TIKTOK_API_KEY", "")
    instagram_access_token: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")

    @property
    def db_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("This MVP supports sqlite:/// DATABASE_URL only.")
        raw_path = self.database_url.replace("sqlite:///", "", 1)
        path = Path(raw_path)
        return path if path.is_absolute() else ROOT_DIR / path


settings = Settings()
