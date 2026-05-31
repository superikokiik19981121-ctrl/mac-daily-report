from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.client_profile import profile
from app.config import ROOT_DIR, settings
from app.report_window import format_window
from app.storage.database import list_report_dates, load_all_items, load_all_summaries

# 競合企業と検出キーワードの定義
COMPETITOR_COMPANIES = [
    ("モスバーガー", ["モスバーガー", "mos burger", "mos.co.jp"]),
    ("バーガーキング", ["バーガーキング", "burger king", "burgerking"]),
    ("KFC", ["ケンタッキー", "kfc", "kentucky fried"]),
    ("ロッテリア", ["ロッテリア", "lotteria"]),
]


def generate_report() -> Path:
    report_dates = list_report_dates()
    reports = {}
    all_items = load_all_items()
    all_summaries = load_all_summaries()
    for report_date in report_dates:
        items = prepare_items(all_items.get(report_date, []))
        competitor_items = [i for i in items if i.get("category") == "competitor"]
        books = [i for i in items if i.get("category") == "books"]
        summary_data = all_summaries.get(report_date, {})
        reports[report_date] = {
            "grouped": group_items(items),
            "competitor_by_company": group_competitors_by_company(competitor_items),
            "competitor_summary": summary_data.get("competitor_summary", ""),
            "books": books,
            "references": items,
            "window": format_window(report_date),
            "digest": build_digest(items),
            "daily_summary": summary_data.get("summary", ""),
        }

    env = Environment(
        loader=FileSystemLoader(ROOT_DIR / "app" / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html.j2")
    html = template.render(
        report_dates=report_dates,
        default_date=report_dates[0] if report_dates else "",
        reports=reports,
    )
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    output_path = settings.report_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def group_competitors_by_company(items: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for company, keywords in COMPETITOR_COMPANIES:
        matched = []
        for item in items:
            haystack = f"{item.get('title','')} {item.get('source_name','')} {item.get('raw_text','')}".lower()
            if any(kw.lower() in haystack for kw in keywords):
                matched.append(item)
        if matched:
            result[company] = matched[:4]
    return result


def group_items(items: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item["platform"] == "youtube":
            grouped["youtube"].append(item)
        elif item["category"] == "sns":
            grouped["sns"].append(item)
        elif item["category"] == "official":
            grouped["official"].append(item)
        elif item["category"] in {"competitor", "news"}:
            grouped["competitor"].append(item)
        elif item["category"] == "trend":
            grouped["trend"].append(item)
    return limit_grouped_items(dict(grouped))


def limit_grouped_items(grouped: dict[str, list[dict]]) -> dict[str, list[dict]]:
    limits = {
        "youtube": 6,
        "official": 8,
        "sns": 6,
        "competitor": 8,
        "trend": 6,
    }
    return {key: values[: limits.get(key, 8)] for key, values in grouped.items()}


def build_digest(items: list[dict]) -> list[str]:
    if not items:
        return ["対象期間内の取得データはありません。"]
    official = [item for item in items if item["category"] == "official"]
    youtube = [item for item in items if item["platform"] == "youtube"]
    competitor = [item for item in items if item["category"] in {"competitor", "news"}]
    digest = []
    if official:
        top = official[0]
        digest.append(
            f"{top['published_display']}時点では、{profile.related_label}で「{top['title']}」が大きな話題です。"
            "商品内容だけでなく、販売状況やSNS反応まで合わせて確認したい流れです。"
        )
    if youtube:
        top = youtube[0]
        digest.append(
            f"YouTubeでは「{top['title']}」が{top['view_count']:,}回再生されています。"
            "サムネイルとタイトルの見せ方は、SNS投稿や店頭訴求の参考になりそうです。"
        )
    if competitor:
        top = competitor[0]
        digest.append(
            f"競合・隣接業界では「{top['title']}」を押さえておきたいです。"
            f"価格、メニュー戦略、デジタル施策の見せ方を{profile.short_name}企画と比較できます。"
        )
    return digest


def prepare_items(items: list[dict]) -> list[dict]:
    prepared = []
    for item in items:
        item = dict(item)
        item["published_display"] = format_datetime(item.get("published_at", ""))
        item["summary_display"] = item.get("one_line_summary") or item.get("original_excerpt") or ""
        if item.get("platform") == "x" and not item.get("impression_count"):
            item["impression_count"] = item.get("view_count", 0)
        prepared.append(item)
    return prepared


def format_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y/%m/%d %H:%M")
    except ValueError:
        return value
