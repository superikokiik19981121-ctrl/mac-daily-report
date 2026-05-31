from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.config import settings


@dataclass(frozen=True)
class OfficialNewsProfile:
    enabled: bool = False
    source_name: str = ""
    url: str = ""
    link_prefix: str = ""


@dataclass(frozen=True)
class ClientProfile:
    brand_name: str = "Client"
    short_name: str = "Client"
    domain_terms: list[str] = field(default_factory=list)
    product_terms: list[str] = field(default_factory=list)
    competitor_terms: list[str] = field(default_factory=list)
    google_news_queries: list[dict[str, Any]] = field(default_factory=list)
    youtube_queries: list[str] = field(default_factory=list)
    related_rules: list[tuple[str, str]] = field(default_factory=list)
    official_news: OfficialNewsProfile = field(default_factory=OfficialNewsProfile)
    messages: dict[str, str] = field(default_factory=dict)

    @property
    def related_label(self) -> str:
        return f"{self.short_name}関連"


def load_client_profile() -> ClientProfile:
    payload = json.loads(settings.client_profile_path.read_text(encoding="utf-8"))
    official = payload.get("official_news") or {}
    return ClientProfile(
        brand_name=payload.get("brand_name", "Client"),
        short_name=payload.get("short_name", payload.get("brand_name", "Client")),
        domain_terms=list(payload.get("domain_terms", [])),
        product_terms=list(payload.get("product_terms", [])),
        competitor_terms=list(payload.get("competitor_terms", [])),
        google_news_queries=list(payload.get("google_news_queries", [])),
        youtube_queries=list(payload.get("youtube_queries", [])),
        related_rules=[tuple(rule) for rule in payload.get("related_rules", [])],
        official_news=OfficialNewsProfile(
            enabled=bool(official.get("enabled")),
            source_name=official.get("source_name", ""),
            url=official.get("url", ""),
            link_prefix=official.get("link_prefix", ""),
        ),
        messages=dict(payload.get("messages", {})),
    )


profile = load_client_profile()
