import re
from typing import Literal

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..auth import require_api_key
from ..config import settings
from ..sns_client import get_sns_client, sns_error_to_http

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(require_api_key)])

_PLATFORM_ARN: dict[str, str] = {
    "ios": "sns_platform_arn_ios",
    "android": "sns_platform_arn_android",
}


class RegisterRequest(BaseModel):
    token: str
    platform: Literal["ios", "android"]
    user_data: str = ""


class RegisterResponse(BaseModel):
    endpoint_arn: str
    created: bool


@router.post("", response_model=RegisterResponse, status_code=status.HTTP_200_OK)
def register_device(body: RegisterRequest):
    platform_arn = getattr(settings, _PLATFORM_ARN[body.platform])
    if not platform_arn:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SNS platform ARN for '{body.platform}' is not configured",
        )

    sns = get_sns_client()
    endpoint_arn: str
    created = False

    try:
        resp = sns.create_platform_endpoint(
            PlatformApplicationArn=platform_arn,
            Token=body.token,
            CustomUserData=body.user_data,
        )
        endpoint_arn = resp["EndpointArn"]
        created = True
    except ClientError as e:
        # SNS raises InvalidParameter when an endpoint with the same token already exists;
        # the existing ARN is embedded in the error message.
        if e.response["Error"]["Code"] != "InvalidParameter":
            raise sns_error_to_http(e)
        match = re.search(r"Endpoint (arn:[^\s]+) already exists", e.response["Error"]["Message"])
        if not match:
            raise sns_error_to_http(e)
        endpoint_arn = match.group(1)

    # Ensure the endpoint is enabled and the stored token matches (handles token rotation).
    try:
        attrs = sns.get_endpoint_attributes(EndpointArn=endpoint_arn)["Attributes"]
        if attrs.get("Enabled", "true").lower() != "true" or attrs.get("Token") != body.token:
            sns.set_endpoint_attributes(
                EndpointArn=endpoint_arn,
                Attributes={"Enabled": "true", "Token": body.token},
            )
    except ClientError as e:
        raise sns_error_to_http(e)

    return RegisterResponse(endpoint_arn=endpoint_arn, created=created)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def deregister_device(endpoint_arn: str = Query(..., description="SNS endpoint ARN to delete")):
    try:
        get_sns_client().delete_endpoint(EndpointArn=endpoint_arn)
    except ClientError as e:
        raise sns_error_to_http(e)
