from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from app.client_profile import profile
from app.report_window import format_window
from app.storage.database import load_all_items


def export_next_data(
    output_path: Path | None = None,
    include_dates: Iterable[date | str] | None = None,
) -> Path:
    target = output_path or Path("next_site/src/data/reportData.json")
    target.parent.mkdir(parents=True, exist_ok=True)

    reports = []
    all_items = load_all_items()
    if include_dates:
        for report_date in include_dates:
            all_items.setdefault(
                report_date.isoformat() if isinstance(report_date, date) else report_date,
                [],
            )

    for report_date in sorted(all_items.keys(), reverse=True):
        items = all_items[report_date]
        prepared = [prepare_item(item) for item in items]
        reports.append(
            {
                "date": report_date,
                "window": format_window(report_date),
                "digest": build_digest(prepared),
                "items": prepared,
            }
        )

    target.write_text(
        json.dumps({"reports": reports}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def prepare_item(item: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(item)
    for key in (
        "like_count",
        "repost_count",
        "comment_count",
        "view_count",
        "impression_count",
    ):
        prepared[key] = int(prepared.get(key) or 0)
    prepared["buzz_score"] = round(float(prepared.get("buzz_score") or 0), 2)
    return prepared


def build_digest(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["対象期間内の新規取得データはありません。ソース設定とAPI接続状態を確認してください。"]

    digest: list[str] = []
    youtube_top = next((item for item in items if item.get("platform") == "youtube"), None)
    news_top = next(
        (
            item
            for item in items
            if item.get("category") in {"official", "news"}
        ),
        None,
    )
    competitor_top = next(
        (item for item in items if item.get("category") == "competitor"),
        None,
    )

    if youtube_top:
        digest.append(
            f"YouTubeでは「{youtube_top['title']}」が{youtube_top['view_count']:,}回再生されています。"
        )
    if news_top:
        digest.append(f"{profile.related_label}ニュースでは「{news_top['title']}」を確認しています。")
    if competitor_top:
        digest.append(
            f"競合・隣接業界では「{competitor_top['title']}」を押さえておきたいです。"
        )

    for item in items:
        if len(digest) >= 3:
            break
        text = item.get("one_line_summary") or item.get("original_excerpt") or item.get("title")
        if text and text not in digest:
            digest.append(text)
    return digest
