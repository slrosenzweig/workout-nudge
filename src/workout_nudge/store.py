"""SQLite persistence: opt_in, daily_status (trained + today_intent), partner_update_sent."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class DailyStatus:
    date: str  # YYYY-MM-DD in America/New_York
    participant: str  # phone E.164
    trained: bool | None  # workout on this calendar day
    source: str | None  # 'oura' | 'sms' | None
    today_intent: str | None  # 'train' | 'rest' | None (intent for this day)


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS opt_in (
                    phone TEXT PRIMARY KEY,
                    opted_in INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS daily_status (
                    date TEXT NOT NULL,
                    participant TEXT NOT NULL,
                    trained INTEGER,
                    source TEXT,
                    today_intent TEXT,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (date, participant)
                );

                CREATE TABLE IF NOT EXISTS partner_update_sent (
                    date TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS comparison_sent (
                    date TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(daily_status)").fetchall()
            }
            if "today_intent" not in cols:
                conn.execute(
                    "ALTER TABLE daily_status ADD COLUMN today_intent TEXT"
                )

    def is_opted_in(self, phone: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT opted_in FROM opt_in WHERE phone = ?", (phone,)
            ).fetchone()
            return bool(row and row["opted_in"])

    def set_opt_in(self, phone: str, opted_in: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO opt_in (phone, opted_in, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(phone) DO UPDATE SET
                    opted_in = excluded.opted_in,
                    updated_at = datetime('now')
                """,
                (phone, 1 if opted_in else 0),
            )

    def get_status(self, date: str, participant: str) -> DailyStatus | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT date, participant, trained, source, today_intent
                FROM daily_status
                WHERE date = ? AND participant = ?
                """,
                (date, participant),
            ).fetchone()
            if not row:
                return None
            trained = row["trained"]
            return DailyStatus(
                date=row["date"],
                participant=row["participant"],
                trained=None if trained is None else bool(trained),
                source=row["source"],
                today_intent=row["today_intent"],
            )

    def set_status(
        self,
        date: str,
        participant: str,
        trained: bool | None,
        source: str | None = None,
    ) -> None:
        """Set yesterday/workout status; preserves today_intent if present."""
        trained_i = None if trained is None else (1 if trained else 0)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO daily_status
                    (date, participant, trained, source, today_intent, updated_at)
                VALUES (?, ?, ?, ?, NULL, datetime('now'))
                ON CONFLICT(date, participant) DO UPDATE SET
                    trained = excluded.trained,
                    source = excluded.source,
                    updated_at = datetime('now')
                """,
                (date, participant, trained_i, source),
            )

    def set_today_intent(
        self,
        date: str,
        participant: str,
        intent: str,
    ) -> None:
        """Set today_intent ('train'|'rest'); preserves trained/source."""
        if intent not in ("train", "rest"):
            raise ValueError(f"invalid today_intent: {intent}")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO daily_status
                    (date, participant, trained, source, today_intent, updated_at)
                VALUES (?, ?, NULL, NULL, ?, datetime('now'))
                ON CONFLICT(date, participant) DO UPDATE SET
                    today_intent = excluded.today_intent,
                    updated_at = datetime('now')
                """,
                (date, participant, intent),
            )

    def partner_update_was_sent(self, date: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM partner_update_sent WHERE date = ?", (date,)
            ).fetchone()
            return row is not None

    def mark_partner_update_sent(self, date: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO partner_update_sent (date, sent_at)
                VALUES (?, datetime('now'))
                ON CONFLICT(date) DO NOTHING
                """,
                (date,),
            )

    # Backward-compatible aliases (old comparison_sent naming)
    def comparison_was_sent(self, date: str) -> bool:
        return self.partner_update_was_sent(date)

    def mark_comparison_sent(self, date: str) -> None:
        self.mark_partner_update_sent(date)

    def yesterday_known(self, date: str, participant: str) -> bool:
        s = self.get_status(date, participant)
        return s is not None and s.trained is not None

    def today_intent_known(self, date: str, participant: str) -> bool:
        s = self.get_status(date, participant)
        return s is not None and s.today_intent in ("train", "rest")

    def participant_complete(
        self, yesterday: str, today: str, participant: str
    ) -> bool:
        return self.yesterday_known(yesterday, participant) and self.today_intent_known(
            today, participant
        )

    def both_complete(
        self, yesterday: str, today: str, a: str, b: str
    ) -> bool:
        return self.participant_complete(
            yesterday, today, a
        ) and self.participant_complete(yesterday, today, b)

    def both_statuses_known(self, date: str, a: str, b: str) -> bool:
        """Legacy: both yesterday trained known for date."""
        return self.yesterday_known(date, a) and self.yesterday_known(date, b)
