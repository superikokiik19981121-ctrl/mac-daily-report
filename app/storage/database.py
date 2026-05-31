from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import sqlite3
from pathlib import Path
from typing import Iterator

from app.config import settings
from app.models import AnalyzedItem


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    published_at TEXT NOT NULL,
    report_date TEXT NOT NULL,
    category TEXT NOT NULL,
    one_line_summary TEXT NOT NULL,
    original_excerpt TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    consumer_reaction TEXT NOT NULL,
    insight_for_brand TEXT NOT NULL,
    buzz_score REAL NOT NULL DEFAULT 0,
    raw_text TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'web',
    like_count INTEGER NOT NULL DEFAULT 0,
    repost_count INTEGER NOT NULL DEFAULT 0,
    comment_count INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER NOT NULL DEFAULT 0,
    impression_count INTEGER NOT NULL DEFAULT 0,
    post_url TEXT,
    thumbnail_url TEXT,
    growth_reason TEXT NOT NULL DEFAULT '',
    sentiment_labels TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_report_date ON items(report_date);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_buzz_score ON items(buzz_score DESC);

CREATE TABLE IF NOT EXISTS daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    competitor_summary TEXT NOT NULL DEFAULT '',
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.db_path) as conn:
        conn.executescript(SCHEMA)
        ensure_columns(conn)


def ensure_columns(conn: sqlite3.Connection) -> None:
    items_existing = {row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    items_columns = {
        "impression_count": "ALTER TABLE items ADD COLUMN impression_count INTEGER NOT NULL DEFAULT 0",
        "thumbnail_url": "ALTER TABLE items ADD COLUMN thumbnail_url TEXT",
    }
    for name, statement in items_columns.items():
        if name not in items_existing:
            conn.execute(statement)

    summary_existing = {row[1] for row in conn.execute("PRAGMA table_info(daily_summary)").fetchall()}
    if "competitor_summary" not in summary_existing:
        conn.execute("ALTER TABLE daily_summary ADD COLUMN competitor_summary TEXT NOT NULL DEFAULT ''")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    init_db()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_items(items: list[AnalyzedItem], report_date: date) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with get_connection() as conn:
        for item in items:
            try:
                conn.execute(
                    """
                    INSERT INTO items (
                        title, source_name, source_url, published_at, report_date, category,
                        one_line_summary, original_excerpt, why_it_matters, consumer_reaction,
                        insight_for_brand, buzz_score, raw_text, platform, like_count,
                        repost_count, comment_count, view_count, impression_count, post_url,
                        thumbnail_url, growth_reason, sentiment_labels
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.title,
                        item.source_name,
                        str(item.source_url),
                        item.published_at.isoformat(),
                        report_date.isoformat(),
                        item.category,
                        item.one_line_summary,
                        item.original_excerpt,
                        item.why_it_matters,
                        item.consumer_reaction,
                        item.insight_for_brand,
                        item.buzz_score,
                        item.raw_text,
                        item.platform,
                        item.like_count,
                        item.repost_count,
                        item.comment_count,
                        item.view_count,
                        item.impression_count,
                        str(item.post_url) if item.post_url else None,
                        str(item.thumbnail_url) if item.thumbnail_url else None,
                        item.growth_reason,
                        ",".join(item.sentiment_labels),
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
    return inserted, skipped


def load_items(report_date: date) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM items
            WHERE report_date = ?
            ORDER BY buzz_score DESC, published_at DESC
            """,
            (report_date.isoformat(),),
        ).fetchall()
    return [dict(row) for row in rows]


def load_all_items() -> dict[str, list[dict]]:
    report_dates = list_report_dates()
    return {report_date: load_items(date.fromisoformat(report_date)) for report_date in report_dates}


def delete_report_date(report_date: date) -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM items WHERE report_date = ?", (report_date.isoformat(),))
        return cursor.rowcount


def latest_report_date() -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(report_date) AS report_date FROM items").fetchone()
    return row["report_date"] if row and row["report_date"] else None


def load_recent_books(days: int = 180) -> list[dict]:
    """直近N日以内に収集した書籍アイテムを返す（重複なし・最新順）"""
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM items
            WHERE category = 'books'
              AND report_date >= ?
            ORDER BY published_at DESC
            LIMIT 20
            """,
            (cutoff,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_report_dates() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT report_date, COUNT(*) AS item_count
            FROM items
            GROUP BY report_date
            ORDER BY report_date DESC
            """
        ).fetchall()
    return [row["report_date"] for row in rows if row["item_count"] > 0]


def save_daily_summary(report_date: date, summary: str, competitor_summary: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_summary (report_date, summary, competitor_summary)
            VALUES (?, ?, ?)
            ON CONFLICT(report_date) DO UPDATE
                SET summary = excluded.summary,
                    competitor_summary = excluded.competitor_summary,
                    generated_at = CURRENT_TIMESTAMP
            """,
            (report_date.isoformat(), summary, competitor_summary),
        )


def load_daily_summary(report_date: date) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT summary FROM daily_summary WHERE report_date = ?",
            (report_date.isoformat(),),
        ).fetchone()
    return row["summary"] if row else ""


def load_all_summaries() -> dict[str, dict[str, str]]:
    """{ report_date: {"summary": ..., "competitor_summary": ...} }"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT report_date, summary, competitor_summary FROM daily_summary ORDER BY report_date DESC"
        ).fetchall()
    return {
        row["report_date"]: {
            "summary": row["summary"],
            "competitor_summary": row["competitor_summary"] or "",
        }
        for row in rows
    }
