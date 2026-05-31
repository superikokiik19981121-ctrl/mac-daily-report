from __future__ import annotations

import json
import logging
import math
import re

from app.client_profile import profile
from app.config import settings
from app.models import AnalyzedItem, RawItem

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """あなたはマクドナルドジャパンのマーケティング担当者向けに、ニュース・SNS・トレンド情報を分析するアナリストです。
与えられた記事を分析し、以下の4項目を必ずJSON形式のみで返してください。前後に説明文やコードブロックは不要です。

{
  "one_line_summary": "1行要約（40字以内）",
  "why_it_matters": "マクドナルド担当者視点でなぜ重要か（50字以内）",
  "consumer_reaction": "生活者の反応・感情（30字以内）",
  "insight_for_brand": "マクドナルドへの示唆・活用アイデア（60字以内）"
}"""

BOOK_SYSTEM_PROMPT = """あなたはマクドナルドジャパンのマーケティング担当者向けに書籍情報を整理するアナリストです。
与えられた書籍情報を分析し、以下の4項目を必ずJSON形式のみで返してください。

{
  "one_line_summary": "書籍の内容を1行で（40字以内）",
  "why_it_matters": "マクドナルド担当者が読む価値がある理由（50字以内）",
  "consumer_reaction": "想定読者・対象層（30字以内）",
  "insight_for_brand": "マクドナルド業務・戦略への活用示唆（60字以内）"
}"""

SENTIMENT_KEYWORDS: dict[str, list[str]] = {
    "驚き": ["びっくり", "意外", "まさか", "衝撃", "予想外"],
    "うまい": ["うまい", "美味しい", "旨い", "おいしい", "最高"],
    "食べたい": ["食べたい", "食べる", "食べてみたい", "気になる", "買う"],
    "懐かしい": ["懐かしい", "復刻", "昔", "平成", "思い出"],
    "高い": ["高い", "値上げ", "価格", "コスパ", "割高"],
    "売り切れ": ["売り切れ", "完売", "在庫", "買えない"],
    "不満": ["不満", "残念", "微妙", "並ぶ", "待ち"],
    "共感": ["わかる", "あるある", "共感", "家族", "子ども"],
}


def analyze_items(items: list[RawItem]) -> list[AnalyzedItem]:
    if settings.groq_api_key:
        return _analyze_with_groq(items)
    return [_analyze_rule_based(item) for item in items]


# ---------- Groq LLM path ----------

def _analyze_with_groq(items: list[RawItem]) -> list[AnalyzedItem]:
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)
    results = []
    for item in items:
        try:
            llm = _call_groq(client, item)
            results.append(_build_from_llm(item, llm))
        except Exception as exc:
            logger.warning("Groq failed for '%s': %s — falling back to rule-based.", item.title, exc)
            results.append(_analyze_rule_based(item))
    return results


def _call_groq(client, item: RawItem) -> dict:
    if item.category == "books":
        return _call_groq_for_book(client, item)

    category_label = {
        "official": "公式発表",
        "news": "業界ニュース",
        "sns": "SNS投稿",
        "trend": "検索トレンド",
        "competitor": "競合情報",
    }.get(item.category, "ニュース")

    user_content = (
        f"カテゴリ: {category_label}\n"
        f"プラットフォーム: {item.platform}\n"
        f"タイトル: {item.title}\n"
        f"内容: {item.original_excerpt or item.raw_text}"
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=400,
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_groq_for_book(client, item: RawItem) -> dict:
    user_content = (
        f"書名: {item.title}\n"
        f"著者: {item.growth_reason.replace('著者: ', '') if item.growth_reason else '不明'}\n"
        f"内容: {item.original_excerpt or item.raw_text}"
    )
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": BOOK_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=400,
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _build_from_llm(item: RawItem, llm: dict) -> AnalyzedItem:
    text = normalize_space(f"{item.title} {item.raw_text}")
    excerpt = item.original_excerpt or make_excerpt(item.raw_text)
    labels = classify_sentiment(text)
    data = item.model_dump()
    data["original_excerpt"] = excerpt
    data.pop("growth_reason", None)  # AnalyzedItem 側で上書きするため除去
    growth = item.growth_reason if item.category == "books" else make_growth_reason(item, labels)
    return AnalyzedItem(
        **data,
        one_line_summary=llm.get("one_line_summary") or item.title,
        why_it_matters=llm.get("why_it_matters") or "",
        consumer_reaction=llm.get("consumer_reaction") or "",
        insight_for_brand=llm.get("insight_for_brand") or "",
        buzz_score=calculate_buzz_score(item, labels),
        growth_reason=growth,
        sentiment_labels=labels,
    )


# ---------- Rule-based fallback ----------

def _analyze_rule_based(item: RawItem) -> AnalyzedItem:
    text = normalize_space(f"{item.title} {item.raw_text}")
    excerpt = item.original_excerpt or make_excerpt(item.raw_text)
    labels = classify_sentiment(text)
    data = item.model_dump()
    data["original_excerpt"] = excerpt
    data.pop("growth_reason", None)  # AnalyzedItem 側で上書きするため除去
    growth = item.growth_reason if item.category == "books" else make_growth_reason(item, labels)
    return AnalyzedItem(
        **data,
        one_line_summary=_make_summary(item),
        why_it_matters=_make_why_it_matters(item, text),
        consumer_reaction=_make_consumer_reaction(item, labels),
        insight_for_brand=_make_insight(item, labels),
        buzz_score=calculate_buzz_score(item, labels),
        growth_reason=growth,
        sentiment_labels=labels,
    )


def _make_summary(item: RawItem) -> str:
    prefix = {
        "official": f"{profile.short_name}/公式発表",
        "news": "業界ニュース",
        "sns": "SNS話題",
        "trend": "検索トレンド",
        "competitor": "競合動向",
        "books": "書籍",
    }.get(item.category, "情報")
    if item.category == "books":
        return f"書籍「{item.title}」がマーケティング担当者の参考になります。"
    return f"{prefix}として「{item.title}」が注目されています。"


def _make_why_it_matters(item: RawItem, text: str) -> str:
    if item.platform == "youtube":
        reason = _extract_related_reason(item.original_excerpt)
        return reason or profile.messages.get("unknown_related", f"{profile.short_name}との関連度は内容確認が必要")
    if item.category == "official":
        return profile.messages.get("official_why", "一次情報として、担当業務の前提確認に直結します。")
    if item.category == "competitor":
        return profile.messages.get("competitor_why", "競合の変化を比較材料として確認します。")
    if item.category == "sns":
        return profile.messages.get("sns_why", "生活者の反応が早く出るため、改善ヒントになります。")
    if "値上げ" in text or "価格" in text:
        return "価格受容性やお得感の見せ方に影響し、購買心理の変化を読む材料になります。"
    return profile.messages.get("default_why", "周辺需要の変化を把握する材料になります。")


def _extract_related_reason(text: str) -> str:
    match = re.search(r"関連理由:\s*(.+)", text)
    return match.group(1).strip() if match else ""


def _make_consumer_reaction(item: RawItem, labels: list[str]) -> str:
    if not labels:
        return "明確な感情ワードは少ないものの、商品名やブランド名への関心が見られます。"
    joined = "・".join(labels)
    if item.platform in {"x", "tiktok", "instagram", "youtube"}:
        return f"SNS上では「{joined}」の反応が中心です。"
    return f"記事内容からは「{joined}」に近い生活者反応が想定されます。"


def _make_insight(item: RawItem, labels: list[str]) -> str:
    if "食べたい" in labels or "うまい" in labels:
        return "実食レビューや旨さの可視化が食欲喚起に効く。短尺動画や写真コンテンツの活用余地があります。"
    if "売り切れ" in labels:
        return "限定感は強い武器ですが、モバイルオーダーや在庫案内の丁寧な告知で不満を抑えられます。"
    if "高い" in labels:
        return "価格訴求だけでなく、ボリューム・満足感・セット割引のお得感をセットで伝える必要があります。"
    if item.category == "competitor":
        return profile.messages.get("competitor_insight", "競合の勝ち筋を自社文脈に翻訳して検討できます。")
    return profile.messages.get("default_insight", "朝会では、どの業務に活かせるかを分けて確認すると使いやすいです。")


# ---------- Shared utilities ----------

def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def make_excerpt(raw_text: str) -> str:
    text = normalize_space(raw_text)
    return text[:160] + ("..." if len(text) > 160 else "")


def calculate_buzz_score(item: RawItem, labels: list[str]) -> float:
    engagement = item.like_count + item.repost_count * 2 + item.comment_count * 3 + item.view_count * 0.01
    weight = {"official": 25, "news": 18, "sns": 10, "trend": 20, "competitor": 16, "books": 14}.get(item.category, 14)
    return round(weight + math.log1p(max(engagement, 0)) * 12 + len(labels) * 3, 2)


def make_growth_reason(item: RawItem, labels: list[str]) -> str:
    if item.platform not in {"x", "tiktok", "instagram", "youtube"}:
        return ""
    reasons = []
    if item.view_count >= 100000:
        reasons.append("再生数が高い")
    if item.comment_count >= 100:
        reasons.append("コメント参加が多い")
    if {"うまい", "食べたい"} & set(labels):
        reasons.append("旨さ・食欲喚起が強い")
    if {"売り切れ", "懐かしい"} & set(labels):
        reasons.append("限定感や記憶喚起が会話化しやすい")
    return "、".join(reasons) if reasons else "商品名とブランド想起が短時間で伝わりやすい"


def classify_sentiment(text: str) -> list[str]:
    return [label for label, kws in SENTIMENT_KEYWORDS.items() if any(kw in text for kw in kws)]
