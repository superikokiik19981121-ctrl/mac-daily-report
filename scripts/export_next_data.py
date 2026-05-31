from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.logging_config import configure_logging
from app.reporting.next_exporter import export_next_data
from app.storage.database import init_db


def main() -> None:
    configure_logging()
    init_db()
    path = export_next_data()
    print(f"Next.js data exported: {path}")


if __name__ == "__main__":
    main()
