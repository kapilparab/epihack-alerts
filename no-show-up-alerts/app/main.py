from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse

from .alerts import build_alert_plan, build_all_scenario_test_alerts
from .database import (
    connect,
    create_user,
    init_db,
    list_outbox,
    list_users,
    list_zip_stats,
    record_alerts,
    reset_db,
    seed_db,
    upsert_zip_stat,
)
from .sendgrid_sender import create_sendgrid_sender_from_env

DEFAULT_DATABASE = Path("data/email_alerts.db")
FIXED_DEMO_NOW = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)


class SendAlertsRequest(BaseModel):
    dry_run: bool = False
    recipient_emails: list[str] | None = Field(default=None)


class CreateUserRequest(BaseModel):
    name: str
    email: str
    zip_code: str
    last_login_at: str
    status: str = "active"


class UpsertZipStatRequest(BaseModel):
    zip_code: str
    population: int
    diseased_count: int


def create_app(
    database_path: str | Path = DEFAULT_DATABASE,
    email_sender: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> FastAPI:
    app = FastAPI(title="Participatory Surveillance Email Alerts")
    connection = connect(database_path)
    init_db(connection)
    configured_email_sender = email_sender if email_sender is not None else create_sendgrid_sender_from_env()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return DEMO_HTML

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "fastapi-email-alerts"}

    @app.post("/seed")
    def seed() -> dict[str, Any]:
        return seed_db(connection)

    @app.post("/reset")
    def reset() -> dict[str, int]:
        return reset_db(connection)

    @app.post("/users")
    def add_user(request: CreateUserRequest) -> dict[str, Any]:
        return create_user(connection, request.model_dump())

    @app.post("/zip-stats")
    def add_zip_stat(request: UpsertZipStatRequest) -> dict[str, Any]:
        return upsert_zip_stat(connection, request.model_dump())

    @app.post("/alerts/preview")
    def preview_alerts() -> dict[str, Any]:
        plan = _current_plan(connection)
        return _serialize_plan(plan)

    @app.post("/alerts/send")
    def send_alerts(request: SendAlertsRequest = SendAlertsRequest()) -> dict[str, Any]:
        plan = _current_plan(connection)
        alerts = _filter_alerts(plan["alerts"], request.recipient_emails)
        filtered_plan = {**plan, "alerts": alerts}

        if not request.dry_run:
            if configured_email_sender is None:
                raise HTTPException(
                    status_code=400,
                    detail="SendGrid is not configured. Set SENDGRID_API_KEY before restarting the server.",
                )
            for alert in alerts:
                try:
                    alert["delivery"] = configured_email_sender(
                        {
                            "to": alert["email"],
                            "to_name": alert["name"],
                            "subject": alert["subject"],
                            "body": alert["body"],
                        }
                    )
                except Exception as exc:
                    raise HTTPException(status_code=502, detail=f"SMTP send failed: {exc}") from exc

        record_alerts(
            connection,
            alerts,
            plan["user_updates"],
            send_status="dry_run" if request.dry_run else "sent",
        )
        return {"dry_run": request.dry_run, **_serialize_plan(filtered_plan)}

    @app.post("/alerts/test-scenarios/send")
    def send_test_scenarios() -> dict[str, Any]:
        if configured_email_sender is None:
            raise HTTPException(
                status_code=400,
                detail="SendGrid is not configured. Set SENDGRID_API_KEY before restarting the server.",
            )
        alerts = build_all_scenario_test_alerts(
            users=list_users(connection),
            login_url="http://localhost:4174/report",
            platform_name="EpiWatch",
        )
        for alert in alerts:
            try:
                alert["delivery"] = configured_email_sender(
                    {
                        "to": alert["email"],
                        "to_name": alert["name"],
                        "subject": alert["subject"],
                        "body": alert["body"],
                    }
                )
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"SendGrid send failed: {exc}") from exc
        record_alerts(connection, alerts, {}, send_status="sent")
        return {"dry_run": False, **_serialize_plan({"alerts": alerts, "user_updates": {}, "zip_risk": []})}

    @app.get("/outbox")
    def outbox() -> dict[str, Any]:
        return {"messages": list_outbox(connection)}

    return app


app = create_app()


def _current_plan(connection) -> dict[str, Any]:
    return build_alert_plan(
        users=list_users(connection),
        zip_stats=list_zip_stats(connection),
        now=FIXED_DEMO_NOW,
        login_url="http://localhost:4174/report",
        platform_name="EpiWatch",
    )


def _serialize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    alerts = plan["alerts"]
    return {
        "alerts": alerts,
        "summary": _summary(alerts),
        "user_updates": plan["user_updates"],
        "zip_risk": plan["zip_risk"],
    }


def _filter_alerts(alerts: list[dict[str, Any]], recipient_emails: list[str] | None) -> list[dict[str, Any]]:
    if not recipient_emails:
        return alerts
    allowed = {email.lower() for email in recipient_emails}
    return [alert for alert in alerts if alert["email"].lower() in allowed]

def _summary(alerts: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": 0, "inactivity": 0, "geographic": 0}
    for alert in alerts:
        summary["total"] += 1
        summary[alert["scenario"]] += 1
    return summary


DEMO_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NO REPORT Alert</title>
  <style>
    :root { --bg:#f7f9fc; --card:#fff; --ink:#172033; --muted:#627083; --line:#dce3ec; --accent:#0f766e; --accent-dark:#115e59; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { max-width: 980px; margin: 0 auto; padding: 36px 20px 52px; }
    h1 { font-size: clamp(32px, 6vw, 54px); line-height: 1; margin: 0 0 12px; }
    .hero { display: grid; gap: 18px; margin-bottom: 24px; }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; }
    button { border: 1px solid var(--line); border-radius: 8px; background: var(--card); color: var(--ink); cursor: pointer; font: inherit; font-size: 14px; font-weight: 700; padding: 11px 14px; }
    button.primary { background: var(--accent); border-color: var(--accent); color: white; }
    button:hover { border-color: var(--accent-dark); }
    .panel { background: var(--card); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 16px 40px rgba(23,32,51,.08); overflow: hidden; }
    .panel-head { align-items: center; border-bottom: 1px solid var(--line); display: flex; gap: 12px; justify-content: space-between; padding: 16px 18px; }
    .panel-head h2 { font-size: 17px; margin: 0; }
    .panel-head span { color: var(--muted); font-size: 13px; }
    .messages { display: grid; gap: 0; }
    .message { border-bottom: 1px solid var(--line); display: grid; gap: 8px; padding: 18px; }
    .message:last-child { border-bottom: 0; }
    .meta { color: var(--muted); font-size: 13px; }
    .badge { background: #e6f5f3; border-radius: 999px; color: var(--accent-dark); display: inline-flex; font-size: 12px; font-weight: 800; padding: 4px 8px; width: max-content; }
    pre { color: var(--ink); font: inherit; line-height: 1.55; margin: 8px 0 0; overflow-x: auto; white-space: pre-wrap; }
    @media (max-width: 640px) { main { padding-top: 24px; } .panel-head { align-items: flex-start; flex-direction: column; } }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div>
        <h1>username -NO REPORT alert</h1>
      </div>
      <div class="controls">
        <button id="preview">Preview alerts</button>
        <button id="send" class="primary">Send alert</button>
        <button id="sendTests">Send every scenario</button>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h2>Generated email messages</h2>
        <span id="status">Ready.</span>
      </div>
      <div id="messages" class="messages"></div>
    </section>
  </main>
  <script>
    const statusEl = document.querySelector("#status");
    const messagesEl = document.querySelector("#messages");
    document.querySelector("#preview").addEventListener("click", () => run("/alerts/preview", "Previewed"));
    document.querySelector("#send").addEventListener("click", () => run("/alerts/send", "Sent"));
    document.querySelector("#sendTests").addEventListener("click", () => run("/alerts/test-scenarios/send", "Sent every scenario"));
    async function run(path, label, body) {
      statusEl.textContent = "Generating messages...";
      const response = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body || {}) });
      const payload = await response.json();
      if (!response.ok) {
        statusEl.textContent = payload.detail || "Request failed.";
        return;
      }
      render(payload.alerts || []);
      statusEl.textContent = `${label}: ${payload.summary.total} total, ${payload.summary.inactivity} inactivity, ${payload.summary.geographic} geographic.`;
    }
    function render(alerts) {
      if (!alerts.length) {
        messagesEl.innerHTML = '<div class="message"><span class="meta">No eligible messages. Seed or reset data to rerun the demo.</span></div>';
        return;
      }
      messagesEl.innerHTML = alerts.map(alert => `
        <article class="message">
          <span class="badge">${escapeHtml(alert.scenario)}</span>
          <strong>${escapeHtml(alert.name)} &lt;${escapeHtml(alert.email)}&gt;</strong>
          <span class="meta">Campaign: ${escapeHtml(alert.campaign_key)} Â· ZIP ${escapeHtml(alert.zip_code)}</span>
          <strong>Subject: ${escapeHtml(alert.subject)}</strong>
          <pre>${escapeHtml(alert.body)}</pre>
        </article>
      `).join("");
    }
    function escapeHtml(value) {
      return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
    }
  </script>
</body>
</html>
"""

