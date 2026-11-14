import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT,
    tariff          TEXT NOT NULL DEFAULT 'free',
    paid_until      INTEGER NOT NULL DEFAULT 0,
    alerts_enabled  INTEGER NOT NULL DEFAULT 1,
    drop_pct        INTEGER NOT NULL DEFAULT 5,
    created_at      INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    last_active_at  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tracks (
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    nm          INTEGER NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    target      INTEGER NOT NULL DEFAULT 0,
    last_price  INTEGER,
    added_at    INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    updated_at  INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    PRIMARY KEY (user_id, nm)
);

CREATE TABLE IF NOT EXISTS payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    amount              INTEGER NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'XTR',
    payload             TEXT NOT NULL DEFAULT '',
    telegram_charge_id  TEXT NOT NULL DEFAULT '',
    created_at          INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_tracks_nm ON tracks (nm);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id);
"""


class Database:
    """Single shared aiosqlite connection with WAL mode."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        logger.info("Database ready: %s", self._path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await self.conn.execute(sql, params)
        await self.conn.commit()

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        cursor = await self.conn.execute(sql, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    async def fetch_one(self, sql: str, params: tuple = ()) -> aiosqlite.Row | None:
        cursor = await self.conn.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetch_value(self, sql: str, params: tuple = ()) -> object:
        row = await self.fetch_one(sql, params)
        return row[0] if row is not None else None
