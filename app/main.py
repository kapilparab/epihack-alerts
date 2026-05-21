from fastapi import FastAPI

from .routers import devices, notifications, subscriptions

app = FastAPI(
    title="Push Notification Service",
    description="SNS-backed push notification microservice for iOS and Android devices.",
    version="1.0.0",
)

app.include_router(devices.router)
app.include_router(subscriptions.router)
app.include_router(notifications.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
