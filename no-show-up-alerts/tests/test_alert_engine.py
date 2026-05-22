from datetime import datetime, timezone

from app.alerts import build_alert_plan, render_email, summarize_zip_risk


NOW = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)


def make_user(**overrides):
    user = {
        "id": 1,
        "name": "hemanth",
        "email": "hemuu077@gmail.com",
        "zip_code": "85001",
        "last_login_at": "2026-05-14T12:00:00+00:00",
        "status": "active",
        "campaigns": set(),
    }
    user.update(overrides)
    return user


def test_selects_inactivity_milestones_at_1_3_5_and_8_weeks():
    users = [
        make_user(id=1, last_login_at="2026-05-14T12:00:00+00:00"),
        make_user(id=2, email="week3@example.com", last_login_at="2026-04-30T12:00:00+00:00"),
        make_user(id=3, email="week5@example.com", last_login_at="2026-04-16T12:00:00+00:00"),
        make_user(id=4, email="week8@example.com", last_login_at="2026-03-26T12:00:00+00:00"),
    ]

    plan = build_alert_plan(users=users, zip_stats=[], now=NOW)

    assert [(alert["user_id"], alert["scenario"], alert["milestone_weeks"]) for alert in plan["alerts"]] == [
        (1, "inactivity", 1),
        (2, "inactivity", 3),
        (3, "inactivity", 5),
        (4, "inactivity", 8),
    ]
    assert plan["user_updates"][4]["status"] == "dormant"


def test_prevents_duplicate_campaigns():
    plan = build_alert_plan(
        users=[make_user(campaigns={"inactivity-1w"})],
        zip_stats=[],
        now=NOW,
    )

    assert plan["alerts"] == []


def test_geographic_activation_targets_inactive_users_at_or_above_ten_percent():
    users = [
        make_user(id=1, zip_code="85001", last_login_at="2026-04-16T12:00:00+00:00"),
        make_user(id=2, email="recent@example.com", zip_code="85001", last_login_at="2026-05-20T12:00:00+00:00"),
        make_user(id=3, email="other@example.com", zip_code="85002", last_login_at="2026-04-16T12:00:00+00:00", campaigns={"inactivity-5w"}),
    ]

    plan = build_alert_plan(
        users=users,
        zip_stats=[
            {"zip_code": "85001", "population": 1000, "diseased_count": 100},
            {"zip_code": "85002", "population": 1000, "diseased_count": 99},
        ],
        now=NOW,
    )

    assert [(alert["user_id"], alert["scenario"], alert["campaign_key"]) for alert in plan["alerts"]] == [
        (1, "geographic", "geo-85001-2026-05-21")
    ]


def test_geographic_activation_overrides_five_week_inactivity():
    user = make_user(id=1, zip_code="85001", last_login_at="2026-04-16T12:00:00+00:00")

    plan = build_alert_plan(
        users=[user],
        zip_stats=[{"zip_code": "85001", "population": 1000, "diseased_count": 125}],
        now=NOW,
    )

    assert len(plan["alerts"]) == 1
    assert plan["alerts"][0]["scenario"] == "geographic"
    assert plan["alerts"][0]["milestone_weeks"] is None


def test_requested_seed_emails_can_receive_both_scenarios():
    users = [
        make_user(id=1, name="hemanth", email="hemuu077@gmail.com", zip_code="85001", last_login_at="2026-05-14T12:00:00+00:00"),
        make_user(id=2, name="Threat Detective", email="threatdetective@gmail.com", zip_code="85002", last_login_at="2026-04-16T12:00:00+00:00"),
    ]

    plan = build_alert_plan(
        users=users,
        zip_stats=[{"zip_code": "85002", "population": 1000, "diseased_count": 110}],
        now=NOW,
    )

    assert [(alert["email"], alert["scenario"]) for alert in plan["alerts"]] == [
        ("hemuu077@gmail.com", "inactivity"),
        ("threatdetective@gmail.com", "geographic"),
    ]


def test_renders_personalized_email_copy():
    email = render_email(
        {
            "scenario": "geographic",
            "name": "hemanth",
            "email": "hemuu077@gmail.com",
            "zip_code": "85001",
            "campaign_key": "geo-85001-2026-05-21",
            "milestone_weeks": None,
        },
        login_url="http://localhost:4174/report",
        platform_name="EpiWatch",
    )

    assert email["subject"] == "Something is happening in your area"
    assert "Hi hemanth," in email["body"]
    assert "more people in your zip code" in email["body"]
    assert "http://localhost:4174/report" in email["body"]
    assert "The EpiWatch team" in email["body"]


def test_summarizes_zip_risk():
    assert summarize_zip_risk([
        {"zip_code": "85001", "population": 1000, "diseased_count": 100},
        {"zip_code": "85002", "population": 0, "diseased_count": 10},
    ]) == [
        {"zip_code": "85001", "population": 1000, "diseased_count": 100, "infection_rate": 0.1, "activated": True},
        {"zip_code": "85002", "population": 0, "diseased_count": 10, "infection_rate": 0, "activated": False},
    ]
