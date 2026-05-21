# epihack-alerts

SNS-backed push notification microservice for iOS and Android devices, built with FastAPI.

## Setup

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Interactive docs: `http://localhost:8000/docs`

## Configuration

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | Yes | Secret key sent in `X-API-Key` header |
| `AWS_REGION` | No | Defaults to `us-east-1` |
| `AWS_ACCESS_KEY_ID` | No | Falls back to default AWS credential chain |
| `AWS_SECRET_ACCESS_KEY` | No | Falls back to default AWS credential chain |
| `SNS_PLATFORM_ARN_IOS` | For iOS | ARN of the APNS SNS platform application |
| `SNS_PLATFORM_ARN_ANDROID` | For Android | ARN of the GCM/FCM SNS platform application |

---

## API reference

All endpoints require the header `X-API-Key: <your-key>`.

### Devices

| Method | Path | Description |
|---|---|---|
| `POST` | `/devices` | Register or refresh a device push token |
| `DELETE` | `/devices?endpoint_arn=...` | Delete a device endpoint |

### Subscriptions

| Method | Path | Description |
|---|---|---|
| `POST` | `/subscriptions` | Subscribe a device endpoint to an SNS topic |
| `DELETE` | `/subscriptions?subscription_arn=...` | Unsubscribe from a topic |

### Notifications

| Method | Path | Description |
|---|---|---|
| `POST` | `/notifications/device` | Push a notification to a specific device |
| `POST` | `/notifications/topic` | Broadcast a notification to all subscribers of a topic |

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (no auth required) |

---

## API flow

### 1. Register a device

Call this when the app starts or receives a new push token from the OS.

```
Mobile App                        This Service                     AWS SNS
    |                                   |                              |
    |-- POST /devices ----------------->|                              |
    |   { token, platform }             |-- create_platform_endpoint ->|
    |                                   |<-- EndpointArn --------------|
    |<-- { endpoint_arn, created } -----|                              |
    |   (store endpoint_arn locally)    |                              |
```

**Request:**
```json
POST /devices
X-API-Key: your-secret-key

{
  "token": "abc123...device-push-token",
  "platform": "ios",
  "user_data": "user-id-456"
}
```

**Response:**
```json
{
  "endpoint_arn": "arn:aws:sns:us-east-1:123:endpoint/APNS/App/guid",
  "created": true
}
```

- `created: false` means the token was already registered — the endpoint is silently refreshed.
- Re-registering with a rotated token (OS-issued new token) updates the existing endpoint automatically.

---

### 2. Subscribe a device to a topic

Use SNS topics for broadcast messages (e.g. "all users", "region-X alerts"). Skip this step for targeted single-device notifications.

**Request:**
```json
POST /subscriptions
X-API-Key: your-secret-key

{
  "endpoint_arn": "arn:aws:sns:...:endpoint/APNS/App/guid",
  "topic_arn":    "arn:aws:sns:us-east-1:123:my-topic"
}
```

**Response:**
```json
{
  "subscription_arn": "arn:aws:sns:us-east-1:123:my-topic:sub-guid"
}
```

---

### 3. Send a notification

**Option A — push to a single device:**
```json
POST /notifications/device
X-API-Key: your-secret-key

{
  "endpoint_arn": "arn:aws:sns:...:endpoint/APNS/App/guid",
  "message": "Your alert is ready",
  "subject": "EpiHack Alert"
}
```

**Option B — platform-specific payloads** (full control over APNS/FCM fields):
```json
POST /notifications/device

{
  "endpoint_arn": "arn:...",
  "message": "fallback text",
  "apns_payload": { "aps": { "alert": "iOS title", "badge": 1, "sound": "default" } },
  "fcm_payload":  { "notification": { "title": "Android title", "body": "body text" } }
}
```

When `apns_payload` or `fcm_payload` are provided, `message` becomes the default fallback and SNS uses `MessageStructure=json` to route each payload to the correct platform.

**Option C — broadcast to a topic:**
```json
POST /notifications/topic

{
  "topic_arn": "arn:aws:sns:us-east-1:123:my-topic",
  "message": "New outbreak alert in your region"
}
```

**Response (all notification endpoints):**
```json
{
  "message_id": "abc-123-sns-message-id"
}
```

---

### 4. Cleanup

**User unsubscribes from a topic:**
```
DELETE /subscriptions?subscription_arn=arn:aws:sns:...:my-topic:sub-guid
→ 204 No Content
```

**User uninstalls or revokes push permission:**
```
DELETE /devices?endpoint_arn=arn:aws:sns:...:endpoint/APNS/App/guid
→ 204 No Content
```

---

### Full lifecycle sequence

```
Install app  →  POST /devices              →  store endpoint_arn
                      ↓
              POST /subscriptions          →  store subscription_arn
                      ↓
              ... time passes ...
                      ↓
Server event  →  POST /notifications/topic    (broadcast)
              or POST /notifications/device   (targeted)
                      ↓
              SNS delivers to APNS / FCM  →  device receives notification
                      ↓
Uninstall     →  DELETE /devices
              →  DELETE /subscriptions
```

The `endpoint_arn` is the stable identifier for a device in SNS. The `subscription_arn` represents one device's membership in one topic — a single device can hold multiple subscriptions.
