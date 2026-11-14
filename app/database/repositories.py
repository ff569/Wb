import time

from app.database.db import Database


class UserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(self, user_id: int, username: str | None, first_name: str | None) -> None:
        await self._db.execute(
            """
            INSERT INTO users (id, username, first_name, last_active_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_active_at = excluded.last_active_at
            """,
            (user_id, username, first_name, int(time.time())),
        )

    async def get(self, user_id: int):
        return await self._db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    async def set_pro(self, user_id: int, paid_until: int) -> None:
        await self._db.execute(
            "UPDATE users SET tariff = 'pro', paid_until = ? WHERE id = ?",
            (paid_until, user_id),
        )

    async def set_alerts_enabled(self, user_id: int, enabled: bool) -> None:
        await self._db.execute(
            "UPDATE users SET alerts_enabled = ? WHERE id = ?",
            (1 if enabled else 0, user_id),
        )

    async def set_drop_pct(self, user_id: int, pct: int) -> None:
        await self._db.execute("UPDATE users SET drop_pct = ? WHERE id = ?", (pct, user_id))

    async def count_active_pro(self, now: int) -> int:
        return await self._db.fetch_value(
            "SELECT COUNT(*) FROM users WHERE paid_until > ?", (now,)
        )

    async def count_all(self) -> int:
        return await self._db.fetch_value("SELECT COUNT(*) FROM users")

    async def count_new_since(self, since: int) -> int:
        return await self._db.fetch_value(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (since,)
        )

    async def all_ids(self) -> list[int]:
        rows = await self._db.fetch_all("SELECT id FROM users")
        return [row["id"] for row in rows]


class TrackRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def count_for_user(self, user_id: int) -> int:
        return await self._db.fetch_value(
            "SELECT COUNT(*) FROM tracks WHERE user_id = ?", (user_id,)
        )

    async def get(self, user_id: int, nm: int):
        return await self._db.fetch_one(
            "SELECT * FROM tracks WHERE user_id = ? AND nm = ?", (user_id, nm)
        )

    async def add(
        self,
        user_id: int,
        nm: int,
        name: str,
        target: int,
        last_price: int | None,
    ) -> None:
        now = int(time.time())
        await self._db.execute(
            """
            INSERT INTO tracks (user_id, nm, name, target, last_price, added_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, nm) DO UPDATE SET
                name = excluded.name,
                target = excluded.target,
                last_price = COALESCE(excluded.last_price, tracks.last_price),
                updated_at = excluded.updated_at
            """,
            (user_id, nm, name, target, last_price, now, now),
        )

    async def list_for_user(self, user_id: int):
        return await self._db.fetch_all(
            "SELECT * FROM tracks WHERE user_id = ? ORDER BY added_at DESC", (user_id,)
        )

    async def delete(self, user_id: int, nm: int) -> bool:
        cursor = await self._db.conn.execute(
            "DELETE FROM tracks WHERE user_id = ? AND nm = ?", (user_id, nm)
        )
        await self._db.conn.commit()
        return cursor.rowcount > 0

    async def distinct_nms(self) -> list[int]:
        rows = await self._db.fetch_all("SELECT DISTINCT nm FROM tracks")
        return [row["nm"] for row in rows]

    async def watchers(self, nm: int):
        return await self._db.fetch_all(
            """
            SELECT t.user_id, t.nm, t.name, t.target, t.last_price,
                   u.alerts_enabled, u.drop_pct
            FROM tracks t
            JOIN users u ON u.id = t.user_id
            WHERE t.nm = ?
            """,
            (nm,),
        )

    async def update_price(self, user_id: int, nm: int, price: int) -> None:
        await self._db.execute(
            "UPDATE tracks SET last_price = ?, updated_at = ? WHERE user_id = ? AND nm = ?",
            (price, int(time.time()), user_id, nm),
        )

    async def count_all(self) -> int:
        return await self._db.fetch_value("SELECT COUNT(*) FROM tracks")


class PaymentRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        user_id: int,
        amount: int,
        currency: str,
        payload: str,
        telegram_charge_id: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO payments (user_id, amount, currency, payload, telegram_charge_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, currency, payload, telegram_charge_id),
        )

    async def exists_charge(self, telegram_charge_id: str) -> bool:
        row = await self._db.fetch_one(
            "SELECT 1 FROM payments WHERE telegram_charge_id = ? LIMIT 1",
            (telegram_charge_id,),
        )
        return row is not None

    async def total_revenue(self) -> int:
        return await self._db.fetch_value("SELECT COALESCE(SUM(amount), 0) FROM payments")

    async def count_all(self) -> int:
        return await self._db.fetch_value("SELECT COUNT(*) FROM payments")

    async def revenue_since(self, since: int) -> int:
        return await self._db.fetch_value(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE created_at >= ?", (since,)
        )
