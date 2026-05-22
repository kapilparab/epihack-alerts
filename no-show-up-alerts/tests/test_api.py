from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path: Path, email_sender=None) -> TestClient:
    return TestClient(create_app(database_path=tmp_path / "email_alerts.db", email_sender=email_sender))


def test_health_returns_service_status(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "fastapi-email-alerts"}


def test_seed_includes_only_reference_testing_emails(tmp_path):
    client = make_client(tmp_path)

    response = client.post("/seed")

    assert response.status_code == 200
    emails = [user["email"] for user in response.json()["users"]]
    assert emails == ["hemuu077@gmail.com", "threatdetective@gmail.com"]


def test_preview_generates_alerts_without_writing_outbox(tmp_path):
    client = make_client(tmp_path)
    client.post("/seed")

    response = client.post("/alerts/preview")
    outbox = client.get("/outbox")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {"total": 2, "inactivity": 1, "geographic": 1}
    assert outbox.json()["messages"] == []


def test_send_records_explicit_dry_run_messages_and_blocks_duplicates(tmp_path):
    client = make_client(tmp_path)
    client.post("/seed")

    first = client.post("/alerts/send", json={"dry_run": True})
    second = client.post("/alerts/send", json={"dry_run": True})
    outbox = client.get("/outbox").json()["messages"]

    assert first.status_code == 200
    assert first.json()["summary"] == {"total": 2, "inactivity": 1, "geographic": 1}
    assert first.json()["dry_run"] is True
    assert second.json()["summary"] == {"total": 0, "inactivity": 0, "geographic": 0}
    assert len(outbox) == 2
    assert {message["send_status"] for message in outbox} == {"dry_run"}


def test_sendgrid_send_requires_api_key_configuration(tmp_path):
    client = make_client(tmp_path)
    client.post("/seed")

    response = client.post("/alerts/send")

    assert response.status_code == 400
    assert "SendGrid" in response.json()["detail"]


def test_real_send_uses_sendgrid_sender_and_records_sent_status(tmp_path):
    sent_messages = []

    def fake_sender(message):
        sent_messages.append(message)
        return {"provider": "sendgrid", "status_code": 202}

    client = make_client(tmp_path, email_sender=fake_sender)
    client.post("/seed")

    response = client.post("/alerts/send")
    outbox = client.get("/outbox").json()["messages"]

    assert response.status_code == 200
    assert response.json()["dry_run"] is False
    assert response.json()["summary"] == {"total": 2, "inactivity": 1, "geographic": 1}
    assert sent_messages[0]["to"] == "hemuu077@gmail.com"
    assert sent_messages[1]["to"] == "threatdetective@gmail.com"
    assert len(outbox) == 2
    assert {message["send_status"] for message in outbox} == {"sent"}


def test_test_scenario_send_delivers_every_template_to_reference_recipients(tmp_path):
    sent_messages = []

    def fake_sender(message):
        sent_messages.append(message)
        return {"provider": "sendgrid", "status_code": 202}

    client = make_client(tmp_path, email_sender=fake_sender)
    client.post("/seed")

    response = client.post("/alerts/test-scenarios/send")
    outbox = client.get("/outbox").json()["messages"]

    assert response.status_code == 200
    assert response.json()["summary"] == {"total": 10, "inactivity": 8, "geographic": 2}
    assert len(sent_messages) == 10
    assert len(outbox) == 10
    assert {message["to"] for message in sent_messages} == {"hemuu077@gmail.com", "threatdetective@gmail.com"}
    assert {
        "Quick check-in",
        "We have not heard from you in a while",
        "Can you check in this week?",
        "Still with us?",
        "Something is happening in your area",
    }.issubset({message["subject"] for message in sent_messages})


def test_reset_restores_seed_data_and_clears_outbox(tmp_path):
    client = make_client(tmp_path)
    client.post("/seed")
    client.post("/alerts/send", json={"dry_run": True})

    response = client.post("/reset")
    outbox = client.get("/outbox")

    assert response.status_code == 200
    assert response.json()["users_count"] == 2
    assert outbox.json()["messages"] == []
