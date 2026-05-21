from functools import lru_cache

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from .config import settings

_SNS_NOT_FOUND_CODES = {"NotFound", "ResourceNotFoundException"}


@lru_cache(maxsize=1)
def get_sns_client():
    kwargs: dict = {"region_name": settings.aws_region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("sns", **kwargs)


def sns_error_to_http(exc: ClientError) -> HTTPException:
    code = exc.response["Error"]["Code"]
    msg = exc.response["Error"]["Message"]
    if code in _SNS_NOT_FOUND_CODES:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if code == "AuthorizationError":
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AWS authorization error")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
