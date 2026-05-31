from __future__ import annotations

import logging
from datetime import date

from app.config import settings
from app.storage.database import load_items

logger = logging.getLogger(__name__)

COMPETITOR_SUMMARY_PROMPT = """あなたはマクドナルドジャパンのマーケティング担当者向けに、競合他社の動きを要約するアナリストです。
本日の競合情報をもとに、100〜150文字で全体要約を作成してください。

要件：
- モスバーガー、バーガーキング、KFC、ロッテリアの動きを中心に言及
- 特に大きな動きがあった企業を優先して簡潔に
- 最後に「マクドナルドとの比較で気になる点」を1文で締める
- 箇条書きではなく自然な日本語の文章
- 動きのない企業は触れない
- データがない場合は「本日は競合に大きな動きは確認されていません。」と返す"""

SUMMARY_PROMPT = """あなたはマクドナルドジャパンの広告代理店向けに朝の日次ブリーフィングを作成するアナリストです。
本日収集した情報をもとに、200〜300文字の日次サマリーを作成してください。

【重要な原則】
- サイトの主役はマクドナルド。マクドナルド自身の動向を必ず中心に置く
- 競合の動きは「マクドナルドとの比較・示唆」として1〜2行以内で補足する
- 書籍情報は担当者の参考として最後に1行追加する（あれば）
- 箇条書きではなく、朝に1分で読める自然な日本語の文章
- 200〜300文字に収める
- 情報がない項目は触れない

含める内容の優先順位：
1. マクドナルド公式の動向（新商品・キャンペーン・IR）
2. SNS・YouTubeでのマクドナルド関連の話題
3. 競合の大きな動き（あれば）
4. 業界・PR関連ニュース
5. 参考書籍（あれば）"""


def generate_competitor_summary(report_date: date) -> str:
    if not settings.groq_api_key:
        return ""
    items = load_items(report_date)
    competitor = [i for i in items if i.get("category") == "competitor"]
    if not competitor:
        return ""
    try:
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        lines = [f"- {i['source_name']}: {i['title']}" for i in competitor[:8]]
        user_content = f"対象日: {report_date.isoformat()}\n\n" + "\n".join(lines)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": COMPETITOR_SUMMARY_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=250,
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        logger.info("競合要約生成完了 (%d文字)", len(result))
        return result
    except Exception as exc:
        logger.warning("競合要約生成に失敗しました: %s", exc)
        return ""


def generate_daily_summary(report_date: date) -> str:
    items = load_items(report_date)
    if not items:
        return ""

    if settings.groq_api_key:
        try:
            return _call_groq_for_summary(items, report_date)
        except Exception as exc:
            logger.warning("Groq失敗のためルールベースサマリーに切替: %s", exc)

    return _rule_based_summary(items, report_date)


def _rule_based_summary(items: list[dict], report_date: date) -> str:
    official = [i for i in items if i.get("category") == "official"]
    youtube = [i for i in items if i.get("platform") == "youtube"]
    competitor = [i for i in items if i.get("category") == "competitor"]
    sns_items = [i for i in items if i.get("category") == "sns" and i.get("platform") != "youtube"]

    parts: list[str] = []

    if official:
        top = official[0]
        parts.append(f"本日のマクドナルド関連では「{top['title']}」が確認されています。")

    if youtube:
        top = youtube[0]
        parts.append(f"YouTubeでは「{top['title']}」が{top.get('view_count', 0):,}回再生されています。")

    if sns_items:
        top = sns_items[0]
        parts.append(f"SNSでは「{top['title']}」が話題になっています。")

    if competitor:
        comp_lines = []
        for i in competitor[:4]:
            company = i.get("source_name", "").replace(" - ニュース", "")
            comp_lines.append(f"{company}「{i['title']}」")
        parts.append("競合では" + "、".join(comp_lines) + "などの動きが確認されています。")

    if not parts:
        titles = "、".join(i["title"] for i in items[:3])
        parts.append(f"本日は{titles}などが収集されました。")

    summary = "".join(parts)
    logger.info("ルールベースサマリー生成完了 (%d文字)", len(summary))
    return summary


def _call_groq_for_summary(items: list[dict], report_date: date) -> str:
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)

    official = [i for i in items if i.get("category") == "official"]
    competitor = [i for i in items if i.get("category") == "competitor"]
    news = [i for i in items if i.get("category") == "news" and i.get("category") != "books"]
    youtube = [i for i in items if i.get("platform") == "youtube"]
    sns_items = [i for i in items if i.get("category") == "sns" and i.get("platform") != "youtube"]
    books = [i for i in items if i.get("category") == "books"]

    sections: list[str] = []

    if official:
        titles = "、".join(i["title"] for i in official[:5])
        sections.append(f"【マクドナルド公式】{titles}")

    if youtube:
        top = youtube[0]
        sections.append(f"【YouTube】「{top['title']}」が{top.get('view_count', 0):,}回再生")

    if sns_items:
        titles = "、".join(i["title"] for i in sns_items[:3])
        sections.append(f"【SNS話題】{titles}")

    if competitor:
        by_company: dict[str, list[str]] = {}
        for item in competitor[:6]:
            src = item.get("source_name", "競合")
            by_company.setdefault(src, []).append(item["title"])
        comp_text = " / ".join(f"{k}: {v[0]}" for k, v in list(by_company.items())[:3])
        sections.append(f"【競合動向】{comp_text}")

    if news:
        titles = "、".join(i["title"] for i in news[:3])
        sections.append(f"【業界ニュース・PR】{titles}")

    if books:
        book_titles = "、".join(f"『{i['title']}』" for i in books[:2])
        sections.append(f"【参考書籍】{book_titles}")

    if not sections:
        return ""

    user_content = f"対象日: {report_date.isoformat()}\n\n" + "\n".join(sections)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=450,
        temperature=0.4,
    )
    summary = response.choices[0].message.content.strip()
    logger.info("日次サマリー生成完了 (%d文字)", len(summary))
    return summary
