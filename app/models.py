from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


Category = Literal["official", "news", "sns", "trend", "competitor", "books"]
Platform = Literal["x", "youtube", "tiktok", "instagram", "web", "google_trends"]


class SourceConfig(BaseModel):
    name: str
    category: Category
    url: HttpUrl
    source_type: Platform = "web"
    enabled: bool = True
    keywords: list[str] = Field(default_factory=list)


class RawItem(BaseModel):
    title: str
    source_name: str
    source_url: HttpUrl
    published_at: datetime
    category: Category
    raw_text: str
    original_excerpt: str = ""
    platform: Platform = "web"
    like_count: int = 0
    repost_count: int = 0
    comment_count: int = 0
    view_count: int = 0
    impression_count: int = 0
    post_url: HttpUrl | None = None
    thumbnail_url: HttpUrl | None = None
    growth_reason: str = ""  # 書籍の著者情報など収集時に確定するメタデータ用


class AnalyzedItem(RawItem):
    one_line_summary: str
    why_it_matters: str
    consumer_reaction: str
    insight_for_brand: str
    buzz_score: float
    growth_reason: str = ""
    sentiment_labels: list[str] = Field(default_factory=list)
