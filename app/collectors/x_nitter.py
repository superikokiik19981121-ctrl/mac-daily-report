from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import re
import xml.etree.ElementTree as ET

import requests

from app.models import RawItem

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
USER_AGENT = "MacDailyReport/0.1 (+local MVP)"
TARGET_ACCOUNT = "McDonaldsJapan"

# 公開 Nitter インスタンス（不安定な場合は順に試みる）
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.catsarch.com",
    "https://nitter.kavin.rocks",
]


def collect_mcdonalds_x(start_at: datetime, end_at: datetime) -> list[RawItem]:
    for instance in NITTER_INSTANCES:
        try:
            items = _fetch_from_instance(instance, start_at, end_at)
            if items is not None:
                logger.info("@%s: Nitter %s から %d件取得", TARGET_ACCOUNT, instance, len(items))
                return items
        except Exception as exc:
            logger.debug("Nitter instance %s failed: %s", instance, exc)

    logger.warning(
        "@%s の取得をスキップしました。すべてのNitterインスタンスが応答しませんでした。",
        TARGET_ACCOUNT,
    )
    return []


def _fetch_from_instance(instance: str, start_at: datetime, end_at: datetime) -> list[RawItem] | None:
    url = f"{instance}/{TARGET_ACCOUNT}/rss"
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()

    # レスポンスが XML でなければスキップ
    content_type = resp.headers.get("content-type", "")
    if "xml" not in content_type and not resp.text.strip().startswith("<"):
        return None

    return _parse_nitter_rss(resp.content, start_at, end_at, instance)


def _parse_nitter_rss(content: bytes, start_at: datetime, end_at: datetime, instance: str) -> list[RawItem]:
    root = ET.fromstring(content)
    items: list[RawItem] = []

    for node in root.findall("./channel/item")[:20]:
        title = _text_of(node, "title")
        link = _text_of(node, "link")
        description = _strip_html(_text_of(node, "description"))
        pub_date_str = _text_of(node, "pubDate")

        if not title or not link:
            continue

        try:
            published_at = _parse_rss_date(pub_date_str)
        except Exception:
            published_at = start_at

        if not (start_at <= published_at < end_at):
            continue

        # nitter.xxx/... → x.com/... に変換
        x_url = re.sub(r"https?://[^/]+/", "https://x.com/", link)
        tweet_text = description or title

        items.append(
            RawItem(
                title=title[:200],
                source_name="X (@McDonaldsJapan)",
                source_url=x_url,
                published_at=published_at,
                category="official",
                raw_text=tweet_text,
                original_excerpt=tweet_text[:180] + ("..." if len(tweet_text) > 180 else ""),
                platform="x",
                post_url=x_url,
            )
        )

    return items


def _text_of(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_rss_date(value: str) -> datetime:
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(JST)
