from __future__ import annotations

import logging
from pathlib import Path

from app.config import ROOT_DIR, settings


def configure_logging() -> None:
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
        ],
    )
