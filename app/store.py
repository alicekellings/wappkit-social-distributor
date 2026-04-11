from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeliveryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    source_slug TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_updated_at TEXT,
                    title TEXT,
                    status TEXT NOT NULL,
                    external_id TEXT,
                    external_url TEXT,
                    platform_state TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform, source_slug)
                )
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(deliveries)").fetchall()
            }
            if "platform_state" not in columns:
                conn.execute("ALTER TABLE deliveries ADD COLUMN platform_state TEXT")
            conn.commit()

    def has_success(self, platform: str, source_slug: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM deliveries
                WHERE platform = ? AND source_slug = ? AND status = 'success'
                LIMIT 1
                """,
                (platform, source_slug),
            ).fetchone()
        return row is not None

    def mark_attempt(
        self,
        platform: str,
        source_slug: str,
        source_url: str,
        title: str,
        source_updated_at: str | None,
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO deliveries (
                    platform,
                    source_slug,
                    source_url,
                    source_updated_at,
                    title,
                    status,
                    attempts,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', 1, ?, ?)
                ON CONFLICT(platform, source_slug) DO UPDATE SET
                    source_url = excluded.source_url,
                    source_updated_at = excluded.source_updated_at,
                    title = excluded.title,
                    attempts = deliveries.attempts + 1,
                    updated_at = excluded.updated_at
                """,
                (platform, source_slug, source_url, source_updated_at, title, now, now),
            )
            conn.commit()

    def mark_success(
        self,
        platform: str,
        source_slug: str,
        external_id: str,
        external_url: str,
        platform_state: dict | str | None = None,
    ) -> None:
        now = utc_now()
        serialized_state: str | None = None
        if platform_state is not None:
            serialized_state = (
                platform_state
                if isinstance(platform_state, str)
                else json.dumps(platform_state, ensure_ascii=False)
            )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE deliveries
                SET status = 'success',
                    external_id = ?,
                    external_url = ?,
                    platform_state = ?,
                    last_error = NULL,
                    updated_at = ?
                WHERE platform = ? AND source_slug = ?
                """,
                (external_id, external_url, serialized_state, now, platform, source_slug),
            )
            conn.commit()

    def mark_failure(self, platform: str, source_slug: str, error_message: str) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE deliveries
                SET status = 'failed',
                    last_error = ?,
                    updated_at = ?
                WHERE platform = ? AND source_slug = ?
                """,
                (error_message[:4000], now, platform, source_slug),
            )
            conn.commit()
