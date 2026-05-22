from __future__ import annotations

import os
from typing import Any, Callable

import httpx


SENDGRID_SEND_URL = "https://api.sendgrid.com/v3/mail/send"
SENDGRID_VERIFIED_SENDERS_URL = "https://api.sendgrid.com/v3/verified_senders"


def create_sendgrid_sender_from_env() -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        return None
    from_email = os.getenv("SENDGRID_FROM_EMAIL") or discover_verified_sender(api_key) or "hemuu077@gmail.com"
    from_name = os.getenv("SENDGRID_FROM_NAME", "Detect Team")
    return create_sendgrid_sender(api_key=api_key, from_email=from_email, from_name=from_name)


def create_sendgrid_sender(*, api_key: str, from_email: str, from_name: str = "Detect Team") -> Callable[[dict[str, Any]], dict[str, Any]]:
    def send(message: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "personalizations": [
                {
                    "to": [{"email": message["to"], "name": message.get("to_name")}],
                    "subject": message["subject"],
                }
            ],
            "from": {"email": from_email, "name": from_name},
            "content": [{"type": "text/plain", "value": message["body"]}],
        }
        response = httpx.post(
            SENDGRID_SEND_URL,
            headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json=payload,
            timeout=20,
        )
        if response.status_code != 202:
            raise RuntimeError(f"SendGrid rejected message with {response.status_code}: {response.text}")
        return {"provider": "sendgrid", "status_code": response.status_code, "from_email": from_email}

    return send


def discover_verified_sender(api_key: str) -> str | None:
    try:
        response = httpx.get(
            SENDGRID_VERIFIED_SENDERS_URL,
            headers={"authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except httpx.HTTPError:
        return None

    if response.status_code != 200:
        return None

    payload = response.json()
    senders = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(senders, list):
        return None

    for sender in senders:
        if sender.get("verified") and sender.get("from_email"):
            return sender["from_email"]
    return None

