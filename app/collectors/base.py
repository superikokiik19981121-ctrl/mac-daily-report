from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.models import RawItem, SourceConfig


class Collector(ABC):
    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    @abstractmethod
    def collect(self, target_date: date) -> list[RawItem]:
        """Collect raw items for one source."""
