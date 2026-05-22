from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  zip_code TEXT NOT NULL,
  last_login_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS zip_stats (
  zip_code TEXT PRIMARY KEY,
  population INTEGER NOT NULL,
  diseased_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS email_campaign_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  campaign_key TEXT NOT NULL,
  scenario TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  send_status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(user_id, campaign_key)
);

CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  recipient_email TEXT NOT NULL,
  recipient_name TEXT NOT NULL,
  scenario TEXT NOT NULL,
  campaign_key TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  send_status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()


def seed_db(connection: sqlite3.Connection) -> dict[str, Any]:
    connection.executescript(
        """
        DELETE FROM outbox;
        DELETE FROM email_campaign_log;
        DELETE FROM users;
        DELETE FROM zip_stats;
        DELETE FROM sqlite_sequence WHERE name IN ('users', 'email_campaign_log', 'outbox');
        """
    )
    connection.executemany(
        """
        INSERT INTO users (name, email, zip_code, last_login_at, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("hemanth", "hemuu077@gmail.com", "85002", "2026-05-14T12:00:00+00:00", "active"),
            ("Threat Detective", "threatdetective@gmail.com", "85001", "2026-04-16T12:00:00+00:00", "active"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO zip_stats (zip_code, population, diseased_count)
        VALUES (?, ?, ?)
        """,
        [
            ("85001", 1000, 115),
            ("85002", 1200, 64),
        ],
    )
    connection.commit()
    return {"users": list_users(connection), "zip_stats": list_zip_stats(connection)}


def reset_db(connection: sqlite3.Connection) -> dict[str, int]:
    seed_db(connection)
    return {"users_count": count_rows(connection, "users"), "zip_stats_count": count_rows(connection, "zip_stats")}


def list_users(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    users = [dict(row) for row in connection.execute("SELECT * FROM users ORDER BY id")]
    campaign_rows = connection.execute("SELECT user_id, campaign_key FROM email_campaign_log").fetchall()
    campaigns_by_user: dict[int, set[str]] = {}
    for row in campaign_rows:
        campaigns_by_user.setdefault(int(row["user_id"]), set()).add(row["campaign_key"])
    for user in users:
        user["campaigns"] = campaigns_by_user.get(int(user["id"]), set())
    return users


def list_zip_stats(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute("SELECT * FROM zip_stats ORDER BY zip_code")]


def list_outbox(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute("SELECT * FROM outbox ORDER BY id")]


def record_alerts(
    connection: sqlite3.Connection,
    alerts: list[dict[str, Any]],
    user_updates: dict[int, dict[str, str]],
    send_status: str = "dry_run",
) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    for alert in alerts:
        connection.execute(
            """
            INSERT OR IGNORE INTO email_campaign_log
              (user_id, campaign_key, scenario, subject, body, send_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert["user_id"],
                alert["campaign_key"],
                alert["scenario"],
                alert["subject"],
                alert["body"],
                send_status,
                created_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO outbox
              (user_id, recipient_email, recipient_name, scenario, campaign_key, subject, body, send_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert["user_id"],
                alert["email"],
                alert["name"],
                alert["scenario"],
                alert["campaign_key"],
                alert["subject"],
                alert["body"],
                send_status,
                created_at,
            ),
        )

    for user_id, update in user_updates.items():
        connection.execute("UPDATE users SET status = ? WHERE id = ?", (update["status"], user_id))
    connection.commit()


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def create_user(connection: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    cursor = connection.execute(
        """
        INSERT INTO users (name, email, zip_code, last_login_at, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user["name"],
            user["email"],
            user["zip_code"],
            user["last_login_at"],
            user.get("status", "active"),
        ),
    )
    connection.commit()
    return dict(connection.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone())


def upsert_zip_stat(connection: sqlite3.Connection, stat: dict[str, Any]) -> dict[str, Any]:
    connection.execute(
        """
        INSERT INTO zip_stats (zip_code, population, diseased_count)
        VALUES (?, ?, ?)
        ON CONFLICT(zip_code) DO UPDATE SET
          population = excluded.population,
          diseased_count = excluded.diseased_count
        """,
        (stat["zip_code"], stat["population"], stat["diseased_count"]),
    )
    connection.commit()
    return dict(connection.execute("SELECT * FROM zip_stats WHERE zip_code = ?", (stat["zip_code"],)).fetchone())
