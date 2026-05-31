from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from app.models import RawItem

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
USER_AGENT = "MacDailyReport/0.1 (+local MVP)"
SEARCH_URL = "https://prtimes.jp/main/html/searchrlp/key/{}"
PRTIMES_BASE = "https://prtimes.jp"
SEARCH_KEYWORDS = ["マクドナルド", "McDonald's", "マック"]


def collect_prtimes_items(start_at: datetime, end_at: datetime) -> list[RawItem]:
    items: list[RawItem] = []
    seen_urls: set[str] = set()
    for keyword in SEARCH_KEYWORDS:
        try:
            url = SEARCH_URL.format(quote_plus(keyword))
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=20,
            )
            resp.raise_for_status()
            new_items = _parse_prtimes_html(resp.content, start_at, end_at, seen_urls)
            items.extend(new_items)
            logger.info("PR TIMES '%s': %d件取得", keyword, len(new_items))
        except Exception as exc:
            logger.warning("PR TIMES collect failed for '%s': %s", keyword, exc)
    return items


def _parse_prtimes_html(
    content: bytes,
    start_at: datetime,
    end_at: datetime,
    seen_urls: set[str],
) -> list[RawItem]:
    soup = BeautifulSoup(content, "html.parser")
    items: list[RawItem] = []

    # PR TIMES の検索結果ページ: article.list-item または div.list-item
    candidates = (
        soup.select("article.list-item")
        or soup.select("div.list-item")
        or soup.select("article[class*='item']")
        or soup.select("li.item")
    )

    for el in candidates:
        try:
            item = _extract_item(el, start_at, end_at, seen_urls)
            if item:
                items.append(item)
        except Exception as exc:
            logger.debug("PR TIMES item parse error: %s", exc)

    # フォールバック: <a> タグから直接抽出
    if not items:
        items = _fallback_parse(soup, start_at, end_at, seen_urls)

    return items


def _extract_item(
    el: BeautifulSoup,
    start_at: datetime,
    end_at: datetime,
    seen_urls: set[str],
) -> RawItem | None:
    # タイトルリンクを探す
    link_el = el.select_one("a[href*='/main/html/rd/p/']") or el.select_one("a[href]")
    if not link_el:
        return None

    title = link_el.get_text(strip=True)
    if not title:
        return None

    href = link_el.get("href", "")
    article_url = href if href.startswith("http") else f"{PRTIMES_BASE}{href}"
    if article_url in seen_urls:
        return None

    # 日付を探す
    date_el = el.select_one("time") or el.select_one("[class*='date']") or el.select_one("[class*='time']")
    published_at = _parse_date_element(date_el) if date_el else None
    if published_at is None:
        published_at = start_at  # 日付不明は収集期間開始時刻で代替

    if not _is_in_window(published_at, start_at, end_at):
        return None

    # 本文スニペット
    desc_el = el.select_one("[class*='summary']") or el.select_one("[class*='desc']") or el.select_one("p")
    description = desc_el.get_text(strip=True) if desc_el else title

    seen_urls.add(article_url)
    return RawItem(
        title=title,
        source_name="PR TIMES",
        source_url=article_url,
        published_at=published_at,
        category="news",
        raw_text=description,
        original_excerpt=description[:180] + ("..." if len(description) > 180 else ""),
        platform="web",
    )


def _fallback_parse(
    soup: BeautifulSoup,
    start_at: datetime,
    end_at: datetime,
    seen_urls: set[str],
) -> list[RawItem]:
    """記事構造が変わった場合のフォールバック: /main/html/rd/p/ を含むリンクを列挙"""
    items: list[RawItem] = []
    for a in soup.select("a[href*='/main/html/rd/p/']"):
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        href = a.get("href", "")
        url = href if href.startswith("http") else f"{PRTIMES_BASE}{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(
            RawItem(
                title=title,
                source_name="PR TIMES",
                source_url=url,
                published_at=start_at,
                category="news",
                raw_text=title,
                original_excerpt=title,
                platform="web",
            )
        )
        if len(items) >= 10:
            break
    return items


def _parse_date_element(el: BeautifulSoup) -> datetime | None:
    # <time datetime="2026-05-31"> 形式
    dt_attr = el.get("datetime", "")
    if dt_attr:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(dt_attr[:19], fmt.replace("%z", ""))
                return dt.replace(tzinfo=JST)
            except ValueError:
                continue

    # テキストから日付を抽出: "2026年05月31日" or "2026.05.31"
    text = el.get_text(strip=True)
    for pattern, fmt in [
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", None),
        (r"(\d{4})\.(\d{1,2})\.(\d{1,2})", None),
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", None),
    ]:
        m = re.search(pattern, text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d, 9, 0, tzinfo=JST)
    return None


def _is_in_window(published_at: datetime, start_at: datetime, end_at: datetime) -> bool:
    return start_at <= published_at < end_at
