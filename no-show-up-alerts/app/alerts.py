from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SECONDS_PER_DAY = 24 * 60 * 60
INACTIVITY_MILESTONES = (1, 3, 5, 8)
ZIP_ACTIVATION_RATE = 0.10
GEOGRAPHIC_INACTIVE_DAYS = 7


def summarize_zip_risk(zip_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks = []
    for stat in zip_stats:
        population = int(stat.get("population") or 0)
        diseased_count = int(stat.get("diseased_count") or 0)
        infection_rate = diseased_count / population if population > 0 else 0
        risks.append(
            {
                "zip_code": str(stat["zip_code"]),
                "population": population,
                "diseased_count": diseased_count,
                "infection_rate": infection_rate,
                "activated": infection_rate >= ZIP_ACTIVATION_RATE,
            }
        )
    return risks


def build_alert_plan(
    *,
    users: list[dict[str, Any]],
    zip_stats: list[dict[str, Any]],
    now: datetime | None = None,
    login_url: str = "http://localhost:4174/report",
    platform_name: str = "EpiWatch",
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    risks = summarize_zip_risk(zip_stats)
    risk_by_zip = {risk["zip_code"]: risk for risk in risks}
    alerts = []
    user_updates: dict[int, dict[str, str]] = {}

    for user in users:
        if not _can_receive_email(user):
            continue

        inactive_days = _days_since(user["last_login_at"], current_time)
        zip_code = str(user["zip_code"])
        risk = risk_by_zip.get(zip_code)

        if risk and risk["activated"] and inactive_days >= GEOGRAPHIC_INACTIVE_DAYS:
            campaign_key = f"geo-{zip_code}-{current_time.date().isoformat()}"
            if not _has_campaign(user, campaign_key):
                alerts.append(
                    _build_alert(
                        user=user,
                        scenario="geographic",
                        campaign_key=campaign_key,
                        milestone_weeks=None,
                        login_url=login_url,
                        platform_name=platform_name,
                    )
                )
            continue

        milestone = _milestone_for_inactive_days(inactive_days)
        if milestone is None:
            continue

        campaign_key = f"inactivity-{milestone}w"
        if _has_campaign(user, campaign_key):
            continue

        alerts.append(
            _build_alert(
                user=user,
                scenario="inactivity",
                campaign_key=campaign_key,
                milestone_weeks=milestone,
                login_url=login_url,
                platform_name=platform_name,
            )
        )
        if milestone == 8:
            user_updates[int(user["id"])] = {"status": "dormant"}

    return {"alerts": alerts, "user_updates": user_updates, "zip_risk": risks}


def build_all_scenario_test_alerts(
    *,
    users: list[dict[str, Any]],
    login_url: str = "http://localhost:4174/report",
    platform_name: str = "EpiWatch",
) -> list[dict[str, Any]]:
    alerts = []
    for user in users:
        if not _can_receive_email(user):
            continue
        for milestone in INACTIVITY_MILESTONES:
            alerts.append(
                _build_alert(
                    user=user,
                    scenario="inactivity",
                    campaign_key=f"test-inactivity-{milestone}w-user-{user['id']}",
                    milestone_weeks=milestone,
                    login_url=login_url,
                    platform_name=platform_name,
                )
            )
        alerts.append(
            _build_alert(
                user=user,
                scenario="geographic",
                campaign_key=f"test-geographic-user-{user['id']}",
                milestone_weeks=None,
                login_url=login_url,
                platform_name=platform_name,
            )
        )
    return alerts


def render_email(
    alert: dict[str, Any],
    *,
    login_url: str = "http://localhost:4174/report",
    platform_name: str = "EpiWatch",
) -> dict[str, str]:
    if alert["scenario"] == "geographic":
        body = "\n".join(
            [
                f"Hi {alert['name']},",
                "",
                "We are reaching out because more people in your zip code have been reporting health symptoms during the past few days. This is exactly the kind of moment where your participation makes a real difference.",
                "",
                'Even if you are feeling fine, please take a minute to log in and share your status. A quick "I am well" report adds important information to what we are seeing locally, and it helps us tell the difference between something spreading and something isolated.',
                "",
                f"Report here: {login_url}",
                "",
                "Thank you for being part of this,",
                f"The {platform_name} team",
            ]
        )
        return {"subject": "Something is happening in your area", "body": body}

    milestone = alert["milestone_weeks"]
    templates = {
        1: (
            "Quick check-in",
            [
                f"Hi {alert['name']},",
                "",
                'It has been a week since your last report. Even if you are feeling fine, that information is useful. A "no symptoms" report takes only a few seconds, and it makes the data from your area more reliable.',
                "",
                f"You can log in here: {login_url}",
                "",
                "Thanks for being part of this,",
                f"The {platform_name} team",
            ],
        ),
        3: (
            "We have not heard from you in a while",
            [
                f"Hi {alert['name']},",
                "",
                "It has been about three weeks since you last checked in. We know life gets busy.",
                "",
                "When you have a moment, please come back and share how you are doing. Your weekly report, even when there is nothing to report, helps us understand what is happening in your community.",
                "",
                f"It takes less than a minute: {login_url}",
                "",
                "Thank you,",
                f"The {platform_name} team",
            ],
        ),
        5: (
            "Can you check in this week?",
            [
                f"Hi {alert['name']},",
                "",
                "It has been about five weeks since your last check-in. Your reports help keep local surveillance data balanced, including weeks when you are feeling healthy.",
                "",
                'If you can, please take a minute to tell us how you are doing. A simple "I am well" update is just as valuable as a symptom report because it helps us understand what is normal in your area.',
                "",
                f"Check in here: {login_url}",
                "",
                "Thank you for continuing to support this work,",
                f"The {platform_name} team",
            ],
        ),
        8: (
            "Still with us?",
            [
                f"Hi {alert['name']},",
                "",
                "It has been two months since we heard from you, and we wanted to reach out before assuming you are no longer interested.",
                "",
                "If you would like to step away, you can unsubscribe at the bottom of this email and we will not contact you again. But if you would like to come back, we would be glad to have you. Even one report a week makes a difference.",
                "",
                f"Log in here: {login_url}",
                "",
                "Either way, thank you for the time you have already given us.",
                f"The {platform_name} team",
            ],
        ),
    }
    subject, lines = templates[milestone]
    return {"subject": subject, "body": "\n".join(lines)}


def _build_alert(
    *,
    user: dict[str, Any],
    scenario: str,
    campaign_key: str,
    milestone_weeks: int | None,
    login_url: str,
    platform_name: str,
) -> dict[str, Any]:
    alert = {
        "user_id": int(user["id"]),
        "name": user["name"],
        "email": user["email"],
        "zip_code": str(user["zip_code"]),
        "scenario": scenario,
        "campaign_key": campaign_key,
        "milestone_weeks": milestone_weeks,
    }
    email = render_email(alert, login_url=login_url, platform_name=platform_name)
    return {**alert, "subject": email["subject"], "body": email["body"]}


def _milestone_for_inactive_days(inactive_days: int) -> int | None:
    for milestone in INACTIVITY_MILESTONES:
        start = milestone * 7
        if start <= inactive_days < start + 7:
            return milestone
    return None


def _days_since(value: str, now: datetime) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int((now - parsed).total_seconds() // SECONDS_PER_DAY)


def _can_receive_email(user: dict[str, Any]) -> bool:
    return bool(user.get("email")) and user.get("status") not in {"unsubscribed", "dormant"}


def _has_campaign(user: dict[str, Any], campaign_key: str) -> bool:
    return campaign_key in set(user.get("campaigns") or [])
