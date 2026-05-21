import json
from typing import Any

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from ..auth import require_api_key
from ..sns_client import get_sns_client, sns_error_to_http

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_api_key)],
)


class DeviceNotificationRequest(BaseModel):
    endpoint_arn: str
    message: str
    subject: str | None = None
    # Optional platform-specific payloads; 'message' becomes the default fallback when provided.
    apns_payload: dict[str, Any] | None = None
    fcm_payload: dict[str, Any] | None = None


class TopicNotificationRequest(BaseModel):
    topic_arn: str
    message: str
    subject: str | None = None


class NotificationResponse(BaseModel):
    message_id: str


@router.post("/device", response_model=NotificationResponse, status_code=status.HTTP_200_OK)
def notify_device(body: DeviceNotificationRequest):
    kwargs: dict[str, Any] = {"TargetArn": body.endpoint_arn}

    if body.apns_payload or body.fcm_payload:
        msg_map: dict[str, str] = {"default": body.message}
        if body.apns_payload:
            msg_map["APNS"] = json.dumps(body.apns_payload)
            msg_map["APNS_SANDBOX"] = json.dumps(body.apns_payload)
        if body.fcm_payload:
            msg_map["GCM"] = json.dumps(body.fcm_payload)
        kwargs["Message"] = json.dumps(msg_map)
        kwargs["MessageStructure"] = "json"
    else:
        kwargs["Message"] = body.message

    if body.subject:
        kwargs["Subject"] = body.subject

    try:
        resp = get_sns_client().publish(**kwargs)
    except ClientError as e:
        raise sns_error_to_http(e)

    return NotificationResponse(message_id=resp["MessageId"])


@router.post("/topic", response_model=NotificationResponse, status_code=status.HTTP_200_OK)
def notify_topic(body: TopicNotificationRequest):
    kwargs: dict[str, Any] = {"TopicArn": body.topic_arn, "Message": body.message}
    if body.subject:
        kwargs["Subject"] = body.subject

    try:
        resp = get_sns_client().publish(**kwargs)
    except ClientError as e:
        raise sns_error_to_http(e)

    return NotificationResponse(message_id=resp["MessageId"])
