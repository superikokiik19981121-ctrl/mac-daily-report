from __future__ import annotations

from datetime import date, datetime
import logging
import re
import unicodedata

from app.client_profile import profile
from app.collectors.books import collect_book_items
from app.collectors.real import collect_real_items
from app.collectors.sample import SampleCollector, load_sources
from app.collectors.x_nitter import collect_mcdonalds_x
from app.collectors.youtube import collect_youtube_items
from app.models import RawItem
from app.report_window import report_window

logger = logging.getLogger(__name__)


def collect_all(
    target_date: date,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[RawItem]:
    start_at, end_at = (start_at, end_at) if start_at and end_at else report_window(target_date)
    collected: list[RawItem] = []

    # Google News（マクドナルド・公式サイト・PR TIMES・競合）
    collected.extend(collect_real_items(target_date, start_at, end_at))

    # YouTube
    try:
        collected.extend(collect_youtube_items(target_date, start_at, end_at))
    except Exception as exc:
        logger.exception("Source failed: YouTube Data API (%s)", exc)

    # @McDonaldsJapan（Nitter RSS 経由・無料・不安定時はスキップ）
    try:
        collected.extend(collect_mcdonalds_x(start_at, end_at))
    except Exception as exc:
        logger.exception("Source failed: X Nitter (%s)", exc)

    # 書籍（Google Books API・時間窓なし・重複は DB の UNIQUE で吸収）
    try:
        collected.extend(collect_book_items())
    except Exception as exc:
        logger.exception("Source failed: Google Books (%s)", exc)

    # サンプルデータ（APIキーなしの動作確認用）
    for source in load_sources():
        try:
            collector = SampleCollector(source)
            collected.extend(collector.collect(target_date))
        except Exception as exc:
            logger.exception("Source failed: %s (%s)", source.name, exc)

    return dedupe_items(collected)


def dedupe_items(items: list[RawItem]) -> list[RawItem]:
    seen: set[str] = set()
    seen_titles: set[str] = set()
    deduped: list[RawItem] = []
    for item in sorted(items, key=lambda value: value.view_count, reverse=True):
        key = str(item.source_url)
        if key in seen:
            logger.info("Duplicate URL skipped: %s", key)
            continue
        title_key = normalize_title(item.title)
        if item.platform != "youtube" and title_key in seen_titles:
            logger.info("Duplicate title skipped: %s", item.title)
            continue
        seen.add(key)
        if item.platform != "youtube":
            seen_titles.add(title_key)
        deduped.append(item)
    return deduped


def normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).lower()
    normalized = re.sub(r"（[^）]*）|\([^)]*\)|【[^】]*】|『|』|「|」", "", normalized)
    normalized = re.sub(r"\s+-\s+.+$", "", normalized)
    aliases = [profile.brand_name, profile.short_name, *profile.product_terms]
    for alias in aliases:
        if alias:
            normalized = normalized.replace(alias.lower(), "brand")
    normalized = re.sub(r"[^0-9a-zぁ-んァ-ン一-龥ー]+", "", normalized)
    return normalized[:80]
