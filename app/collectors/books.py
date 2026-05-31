from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import xml.etree.ElementTree as ET

import requests

from app.models import RawItem

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

# 国立国会図書館 OpenSearch API（完全無料・APIキー不要）
NDL_URL = "https://iss.ndl.go.jp/api/opensearch"
DC_NS = "http://purl.org/dc/elements/1.1/"

BOOK_QUERIES = [
    ("マクドナルド", 8),
    ("McDonald's 日本", 4),
]

LOOKBACK_YEARS = 2


def collect_book_items() -> list[RawItem]:
    items: list[RawItem] = []
    seen_urls: set[str] = set()
    cutoff_year = datetime.now(JST).year - LOOKBACK_YEARS

    for query, max_results in BOOK_QUERIES:
        try:
            new = _search_ndl(query, max_results, cutoff_year, seen_urls)
            items.extend(new)
            logger.info("NDL書籍 '%s': %d件取得", query, len(new))
        except Exception as exc:
            logger.warning("NDL書籍検索失敗 '%s': %s", query, exc)

    return items


def _search_ndl(
    query: str,
    max_results: int,
    cutoff_year: int,
    seen_urls: set[str],
) -> list[RawItem]:
    params = {
        "any": query,
        "cnt": max_results * 3,
        "from": str(cutoff_year),
    }
    resp = requests.get(
        NDL_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    items: list[RawItem] = []

    for node in root.findall(".//item"):
        title = _text(node, "title") or ""
        link  = _text(node, "link") or ""
        if not title or not link or link in seen_urls:
            continue

        # タイトルに「マクドナルド」または「McDonald」を含むもののみ
        if "マクドナルド" not in title and "McDonald" not in title:
            continue

        author    = _dc(node, "creator") or "不明"
        publisher = _dc(node, "publisher") or ""
        date_str  = _dc(node, "date") or ""
        subject   = _dc(node, "subject") or ""
        desc      = _text(node, "description") or subject or title

        published_at = _parse_date(date_str)
        if published_at.year < cutoff_year:
            continue

        excerpt = f"著者: {author}" + (f" / {publisher}" if publisher else "") + f"\n{desc}"

        seen_urls.add(link)
        items.append(
            RawItem(
                title=title,
                source_name="国立国会図書館",
                source_url=link,
                published_at=published_at,
                category="books",
                raw_text=f"{title} {desc}",
                original_excerpt=excerpt[:300],
                platform="web",
                growth_reason=f"著者: {author}",
            )
        )
        if len(items) >= max_results:
            break

    return items


def _text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _dc(node: ET.Element, field: str) -> str:
    child = node.find(f"{{{DC_NS}}}{field}")
    return (child.text or "").strip() if child is not None else ""


def _parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value[:len(fmt)], fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return datetime.now(JST)
