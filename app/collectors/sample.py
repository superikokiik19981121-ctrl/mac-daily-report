from __future__ import annotations

from datetime import date, datetime
import json
import logging

from app.collectors.base import Collector
from app.config import settings
from app.models import RawItem, SourceConfig

logger = logging.getLogger(__name__)


class SampleCollector(Collector):
    def collect(self, target_date: date) -> list[RawItem]:
        payload = json.loads(settings.sample_data_path.read_text(encoding="utf-8"))
        items = []
        for item in payload.get("items", []):
            if item.get("source_name") != self.source.name:
                continue
            published_at = datetime.fromisoformat(item["published_at"])
            if published_at.date() != target_date:
                continue
            items.append(RawItem(**item))
        return items


def load_sources() -> list[SourceConfig]:
    payload = json.loads(settings.sample_data_path.read_text(encoding="utf-8"))
    return [SourceConfig(**source) for source in payload.get("sources", []) if source.get("enabled", True)]
