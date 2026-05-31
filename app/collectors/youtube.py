from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import unicodedata

import requests

from app.client_profile import profile
from app.config import settings
from app.models import RawItem

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def collect_youtube_items(target_date: date, start_at: datetime, end_at: datetime) -> list[RawItem]:
    if not settings.youtube_api_key:
        logger.info("YouTube API key is not set. Skipping YouTube collector.")
        return []

    video_ids = search_video_ids(start_at, end_at)
    if not video_ids:
        return []
    return fetch_video_items(video_ids, start_at, end_at)


def search_video_ids(start_at: datetime, end_at: datetime) -> list[str]:
    published_after = start_at.astimezone(timezone.utc)
    published_before = end_at.astimezone(timezone.utc)
    seen: set[str] = set()
    video_ids: list[str] = []
    for query in profile.youtube_queries:
        params = {
            "key": settings.youtube_api_key,
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": 10,
            "order": "viewCount",
            "regionCode": "JP",
            "relevanceLanguage": "ja",
            "publishedAfter": published_after.isoformat().replace("+00:00", "Z"),
            "publishedBefore": published_before.isoformat().replace("+00:00", "Z"),
        }
        response = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=20)
        response.raise_for_status()
        for item in response.json().get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if video_id and video_id not in seen:
                seen.add(video_id)
                video_ids.append(video_id)
    return video_ids


def fetch_video_items(video_ids: list[str], start_at: datetime, end_at: datetime) -> list[RawItem]:
    items: list[RawItem] = []
    for chunk in chunked(video_ids, 50):
        params = {
            "key": settings.youtube_api_key,
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "maxResults": 50,
        }
        response = requests.get(YOUTUBE_VIDEOS_URL, params=params, timeout=20)
        response.raise_for_status()
        for item in response.json().get("items", []):
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            content_details = item.get("contentDetails", {})
            published_at = parse_youtube_datetime(snippet.get("publishedAt", ""))
            if not (start_at <= published_at < end_at):
                continue
            video_id = item["id"]
            title = snippet.get("title", "")
            description = snippet.get("description", "")
            channel_title = snippet.get("channelTitle", "YouTube")
            if not is_relevant_to_brand(title, description, channel_title):
                logger.info("Skipping weakly related YouTube item: %s", title)
                continue
            thumbnail_url = pick_thumbnail(snippet.get("thumbnails", {}))
            duration_seconds = parse_duration_seconds(content_details.get("duration", ""))
            is_short = is_youtube_short(title, description, duration_seconds)
            related_reason = make_related_reason(title, description, channel_title)
            excerpt = make_excerpt(description or title)
            if related_reason:
                excerpt = f"{excerpt}\n関連理由: {related_reason}"
            if is_short:
                excerpt = f"{excerpt}\n形式: YouTube Shorts/短尺動画"
            items.append(
                RawItem(
                    title=title,
                    source_name=f"YouTube - {channel_title}",
                    source_url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=published_at,
                    category="sns",
                    raw_text=description or title,
                    original_excerpt=excerpt,
                    platform="youtube",
                    like_count=parse_int(statistics.get("likeCount")),
                    comment_count=parse_int(statistics.get("commentCount")),
                    view_count=parse_int(statistics.get("viewCount")),
                    post_url=f"https://www.youtube.com/watch?v={video_id}",
                    thumbnail_url=thumbnail_url,
                )
            )
    return sorted(items, key=lambda item: item.view_count, reverse=True)


def is_relevant_to_brand(title: str, description: str, channel_title: str) -> bool:
    text = unicodedata.normalize("NFKC", f"{title} {description} {channel_title}").lower()
    all_terms = (
        [profile.brand_name, profile.short_name, "mcdonald", "mcdonalds"]
        + profile.domain_terms
        + profile.product_terms
    )
    return any(term.lower() in text for term in all_terms if term)


def parse_youtube_datetime(value: str) -> datetime:
    if not value:
        return datetime.now(JST)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(JST)


def pick_thumbnail(thumbnails: dict) -> str | None:
    for key in ("maxres", "standard", "high", "medium", "default"):
        thumbnail = thumbnails.get(key)
        if thumbnail and thumbnail.get("url"):
            return thumbnail["url"]
    return None


def is_youtube_short(title: str, description: str, duration_seconds: int) -> bool:
    text = f"{title} {description}".lower()
    return duration_seconds <= 60 or "#shorts" in text or "shorts" in text or "ショート" in text


def parse_duration_seconds(value: str) -> int:
    if not value:
        return 0
    match = __import__("re").match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def make_related_reason(title: str, description: str, channel_title: str) -> str:
    text = f"{title} {description} {channel_title}".lower()
    reasons = [reason for keyword, reason in profile.related_rules if keyword.lower() in text]
    if not reasons:
        return "検索語に関連して取得。内容確認が必要"
    return "、".join(dict.fromkeys(reasons[:3]))


def parse_int(value: str | int | None) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def make_excerpt(value: str) -> str:
    value = " ".join(value.split())
    return value[:180] + ("..." if len(value) > 180 else "")


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
