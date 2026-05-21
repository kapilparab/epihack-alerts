from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from ..auth import require_api_key
from ..sns_client import get_sns_client, sns_error_to_http

router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"],
    dependencies=[Depends(require_api_key)],
)


class SubscribeRequest(BaseModel):
    endpoint_arn: str
    topic_arn: str


class SubscribeResponse(BaseModel):
    subscription_arn: str


@router.post("", response_model=SubscribeResponse, status_code=status.HTTP_200_OK)
def subscribe(body: SubscribeRequest):
    try:
        resp = get_sns_client().subscribe(
            TopicArn=body.topic_arn,
            Protocol="application",
            Endpoint=body.endpoint_arn,
            ReturnSubscriptionArn=True,
        )
    except ClientError as e:
        raise sns_error_to_http(e)
    return SubscribeResponse(subscription_arn=resp["SubscriptionArn"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(subscription_arn: str = Query(..., description="SNS subscription ARN to remove")):
    try:
        get_sns_client().unsubscribe(SubscriptionArn=subscription_arn)
    except ClientError as e:
        raise sns_error_to_http(e)
