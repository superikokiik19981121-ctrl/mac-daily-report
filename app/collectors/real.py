from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import re
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests
import urllib3

from app.client_profile import profile
from app.models import RawItem

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def collect_real_items(target_date: date, start_at: datetime, end_at: datetime) -> list[RawItem]:
    items: list[RawItem] = []
    for source in profile.google_news_queries:
        try:
            items.extend(collect_google_news(source, start_at, end_at))
        except Exception as exc:
            logger.exception("Source failed: %s (%s)", source["source_name"], exc)
    if profile.official_news.enabled:
        try:
            items.extend(collect_official_news_release(start_at, end_at))
        except Exception as exc:
            logger.exception("Source failed: %s (%s)", profile.official_news.source_name, exc)
    return items


def collect_google_news(source: dict, start_at: datetime, end_at: datetime) -> list[RawItem]:
    query = quote_plus(f"{source['query']} when:7d")
    url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
    response = safe_get(url)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: list[RawItem] = []
    for node in root.findall("./channel/item")[:15]:
        title = text_of(node, "title")
        link = text_of(node, "link")
        description = strip_html(text_of(node, "description"))
        published_at = parse_rss_date(text_of(node, "pubDate"))
        if not is_in_window(published_at, start_at, end_at):
            continue
        haystack = f"{title} {description}"
        if not any(keyword in haystack for keyword in source["keywords"]):
            continue
        items.append(
            RawItem(
                title=clean_google_title(title),
                source_name=source["source_name"],
                source_url=link,
                published_at=published_at,
                category=source["category"],
                raw_text=description or title,
                original_excerpt=make_excerpt(description or title),
                platform="web",
            )
        )
    return items


def collect_official_news_release(start_at: datetime, end_at: datetime) -> list[RawItem]:
    url = profile.official_news.url
    if not url:
        return []
    response = safe_get(url)
    response.raise_for_status()
    html = response.text
    pattern = re.compile(
        r"(?P<date>20\d{2}\.\d{1,2}\.\d{1,2}).{0,300}?(?P<href>/company/news/[^\"']+)[^>]*>(?P<title>[^<]+)</a>",
        re.DOTALL,
    )
    items: list[RawItem] = []
    for match in pattern.finditer(html):
        published_at = parse_brand_date(match.group("date"))
        title = strip_html(match.group("title")).strip()
        if not title:
            continue
        if not is_in_window(published_at, start_at - timedelta(days=1), end_at):
            continue
        href = match.group("href")
        link = f"{profile.official_news.link_prefix}{href}" if href.startswith("/") else href
        items.append(
            RawItem(
                title=title,
                source_name=profile.official_news.source_name or f"{profile.brand_name}公式ニュース",
                source_url=link,
                published_at=published_at,
                category="official",
                raw_text=title,
                original_excerpt=make_excerpt(title),
                platform="web",
            )
        )
    return items


def text_of(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def safe_get(url: str) -> requests.Response:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
        return response
    except requests.exceptions.SSLError:
        logger.warning("SSL verification failed, retrying without verification: %s", url)
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, verify=False)
        response.raise_for_status()
        return response


def parse_rss_date(value: str) -> datetime:
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(JST)


def parse_brand_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y.%m.%d").replace(tzinfo=JST)


def is_in_window(published_at: datetime, start_at: datetime, end_at: datetime) -> bool:
    return start_at <= published_at < end_at


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def clean_google_title(title: str) -> str:
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def make_excerpt(value: str) -> str:
    value = strip_html(value)
    return value[:180] + ("..." if len(value) > 180 else "")
