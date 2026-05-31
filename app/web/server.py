from __future__ import annotations

import logging
from datetime import date

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from app.config import settings
from app.reporting.generator import generate_report
from app.storage.database import list_report_dates, load_items

logger = logging.getLogger(__name__)
app = FastAPI(title=settings.app_name)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if list_report_dates():
        path = generate_report()
    else:
        path = settings.report_dir / "index.html"
        if not path.exists():
            return HTMLResponse("<h1>No report data</h1><p>Run collect first.</p>", status_code=200)
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/items/{report_date}")
def api_items(report_date: date) -> list[dict]:
    return load_items(report_date)


@app.get("/api/report-dates")
def api_report_dates() -> list[str]:
    return list_report_dates()


@app.get("/reports/index.html", response_class=HTMLResponse)
def report_index() -> HTMLResponse:
    return index()


@app.post("/trigger")
def trigger_update(
    background_tasks: BackgroundTasks,
    x_cron_secret: str | None = Header(None),
) -> dict[str, str]:
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Cron-Secret header")
    background_tasks.add_task(_run_daily_update)
    return {"status": "triggered"}


def _run_daily_update() -> None:
    from app.analysis.analyzer import analyze_items
    from app.collectors.registry import collect_all
    from app.logging_config import configure_logging
    from app.report_window import report_window, today_report_date
    from app.reporting.next_exporter import export_next_data
    from app.storage.database import init_db, save_items

    configure_logging()
    init_db()
    target_date = today_report_date()
    start_at, end_at = report_window(target_date)
    raw_items = collect_all(target_date, start_at, end_at)
    analyzed = analyze_items(raw_items)
    inserted, skipped = save_items(analyzed, target_date)
    export_next_data(include_dates=[target_date])
    logger.info("Trigger update done: %d inserted, %d skipped", inserted, skipped)
