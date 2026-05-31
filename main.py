from __future__ import annotations

from datetime import date, datetime, timedelta

import typer
import uvicorn
from rich.console import Console

from app.analysis.analyzer import analyze_items
from app.analysis.daily_summary import generate_competitor_summary, generate_daily_summary
from app.collectors.registry import collect_all
from app.logging_config import configure_logging
from app.reporting.next_exporter import export_next_data
from app.report_window import report_window, today_report_date
from app.storage.database import delete_report_date, init_db, save_daily_summary, save_items
from app.web.server import app as fastapi_app


cli = typer.Typer(help="マクドナルド日次レポート生成CLI")
console = Console()


@cli.command()
def collect(date_: str = typer.Option(..., "--date", help="収集対象日 YYYY-MM-DD")) -> None:
    configure_logging()
    init_db()
    target_date = parse_date(date_)
    start_at, end_at = report_window(target_date)
    raw_items = collect_all(target_date, start_at, end_at)
    analyzed = analyze_items(raw_items)
    inserted, skipped = save_items(analyzed, target_date)
    console.print(f"収集期間: {start_at:%Y-%m-%d %H:%M} - {end_at:%Y-%m-%d %H:%M}")
    console.print(f"収集完了: {len(raw_items)}件 / 保存 {inserted}件 / 重複スキップ {skipped}件")


@cli.command("daily-update")
def daily_update(date_: str | None = typer.Option(None, "--date", help="更新日 YYYY-MM-DD。未指定なら今日")) -> None:
    configure_logging()
    init_db()
    target_date = parse_date(date_) if date_ else today_report_date()
    start_at, end_at = report_window(target_date)
    raw_items = collect_all(target_date, start_at, end_at)
    analyzed = analyze_items(raw_items)
    inserted, skipped = save_items(analyzed, target_date)
    summary = generate_daily_summary(target_date)
    competitor_summary = generate_competitor_summary(target_date)
    if summary or competitor_summary:
        save_daily_summary(target_date, summary, competitor_summary)
    path = export_next_data(include_dates=[target_date])
    console.print(f"日次更新日: {target_date.isoformat()}")
    console.print(f"収集期間: {start_at:%Y-%m-%d %H:%M} - {end_at:%Y-%m-%d %H:%M}")
    console.print(f"収集完了: {len(raw_items)}件 / 保存 {inserted}件 / 重複スキップ {skipped}件")
    if summary:
        console.print(f"AIサマリー生成完了 ({len(summary)}文字)")
    console.print(f"Next.jsデータ更新完了: {path}")


@cli.command()
def generate() -> None:
    configure_logging()
    init_db()
    path = export_next_data()
    console.print(f"Next.jsデータ更新完了: {path}")


@cli.command("delete-date")
def delete_date(date_: str = typer.Option(..., "--date", help="削除対象日 YYYY-MM-DD")) -> None:
    configure_logging()
    init_db()
    target_date = parse_date(date_)
    deleted = delete_report_date(target_date)
    path = export_next_data()
    console.print(f"削除完了: {target_date.isoformat()} / {deleted}件")
    console.print(f"Next.jsデータ更新完了: {path}")


@cli.command()
def backfill(
    from_: str = typer.Option(..., "--from", help="開始日 YYYY-MM-DD"),
    to_: str | None = typer.Option(None, "--to", help="終了日 YYYY-MM-DD（省略時は今日）"),
) -> None:
    """指定期間のデータを一括収集・AI分析して保存する"""
    configure_logging()
    init_db()
    start_date = parse_date(from_)
    end_date = parse_date(to_) if to_ else today_report_date()

    if start_date > end_date:
        console.print("[red]開始日が終了日より後になっています。[/red]")
        raise typer.Exit(1)

    total_days = (end_date - start_date).days + 1
    console.print(f"バックフィル開始: {start_date} 〜 {end_date} ({total_days}日分)")

    current = start_date
    while current <= end_date:
        start_at, end_at = report_window(current)
        console.print(f"\n[bold]{current}[/bold] 収集中 ({start_at:%m/%d %H:%M}〜{end_at:%m/%d %H:%M})...")
        raw_items = collect_all(current, start_at, end_at)
        analyzed = analyze_items(raw_items)
        inserted, skipped = save_items(analyzed, current)
        summary = generate_daily_summary(current)
        competitor_summary = generate_competitor_summary(current)
        if summary or competitor_summary:
            save_daily_summary(current, summary, competitor_summary)
        console.print(
            f"  収集 {len(raw_items)}件 / 保存 {inserted}件 / スキップ {skipped}件"
            + (f" / AIサマリー {len(summary)}文字" if summary else "")
        )
        current += timedelta(days=1)

    path = export_next_data()
    console.print(f"\nバックフィル完了。レポート生成: {path}")


@cli.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    configure_logging()
    init_db()
    console.print(f"起動中: http://{host}:{port}")
    uvicorn.run(fastapi_app, host=host, port=port)


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter("日付は YYYY-MM-DD 形式で指定してください。") from exc


if __name__ == "__main__":
    cli()
