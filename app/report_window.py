from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone


JST = timezone(timedelta(hours=9))


def report_window(report_date: date) -> tuple[datetime, datetime]:
    """report_date の 00:00 JST〜翌日 00:00 JST（1日全体）を対象とする"""
    start_at = datetime.combine(report_date, time(0, 0, 0), JST)
    end_at = datetime.combine(report_date + timedelta(days=1), time(0, 0, 0), JST)
    return start_at, end_at


def today_report_date() -> date:
    """6:00 AM 実行時に前日 1 日分を収集するため、report_date = 昨日とする"""
    return (datetime.now(JST) - timedelta(days=1)).date()


def format_window(report_date: str) -> str:
    parsed = date.fromisoformat(report_date)
    start_at, end_at = report_window(parsed)
    return f"{start_at:%Y/%m/%d %H:%M} - {end_at:%Y/%m/%d %H:%M}"
