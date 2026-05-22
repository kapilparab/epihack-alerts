# No Show Up Alerts

FastAPI + SQLite microservice for participatory-surveillance email alerts when users stop reporting, plus a geographic activation alert when a zip code reaches a 10% diseased/reporting threshold.

## What it does

- Sends inactivity alerts at 1, 3, 5, and 8 weeks since last login.
- Sends a geographic activation alert when `diseased_count / population >= 0.10` for the user's zip code.
- Uses SQLite for users, zip-code stats, campaign logs, and send outbox records.
- Sends mail through SendGrid Mail Send API.
- Provides integration endpoints for larger user pools.

## Run

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 4174
```

Set SendGrid configuration through environment variables. Never commit real keys.

```powershell
$env:SENDGRID_API_KEY="your-sendgrid-api-key"
$env:SENDGRID_FROM_EMAIL="verified-sender@example.com"
$env:SENDGRID_FROM_NAME="Detect Team"
python -m uvicorn app.main:app --host 127.0.0.1 --port 4174
```

## Integration endpoints

- `GET /health`
- `POST /seed` for local reference data only
- `POST /users` to add a user
- `POST /zip-stats` to create or update zip disease stats
- `POST /alerts/preview` to preview currently eligible alerts
- `POST /alerts/send` to send currently eligible alerts through SendGrid
- `POST /alerts/test-scenarios/send` to send every scenario template to seeded reference users for QA
- `GET /outbox` to inspect recorded send attempts
- `POST /reset` to reset local demo data

## Tests

```bash
python -m pytest
```

## Security note

SendGrid API keys must be supplied only through environment variables or a secret manager. If a key is exposed in chat, logs, or source control, rotate it immediately.
