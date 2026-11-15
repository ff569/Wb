import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    webhook_url: str
    webhook_path: str
    webhook_secret: str
    db_path: str
    port: int
    check_interval: int
    free_limit: int
    pro_limit: int
    pro_price_stars: int
    pro_days: int
    default_drop_pct: int
    support_url: str
    proxy_url: str


def _parse_admin_ids(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return tuple(ids)


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Add it in Render -> Environment "
            "or export BOT_TOKEN locally."
        )

    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", "") or os.getenv("ADMIN_ID", ""))
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS is not set. Put your Telegram ID there (from @userinfobot).")

    return Settings(
        bot_token=bot_token,
        admin_ids=admin_ids,
        webhook_url=os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/"),
        webhook_path=os.getenv("WEBHOOK_PATH", "/webhook"),
        webhook_secret=os.getenv("WEBHOOK_SECRET", "").strip(),
        db_path=os.getenv("DB_PATH", "wb_detector.db"),
        port=int(os.getenv("PORT", "8080")),
        check_interval=int(os.getenv("CHECK_INTERVAL", "3600")),
        free_limit=int(os.getenv("FREE_LIMIT", "3")),
        pro_limit=int(os.getenv("PRO_LIMIT", "50")),
        pro_price_stars=int(os.getenv("PRO_PRICE_STARS", "300")),
        pro_days=int(os.getenv("PRO_DAYS", "30")),
        default_drop_pct=int(os.getenv("DEFAULT_DROP_PCT", "5")),
        support_url=os.getenv("SUPPORT_URL", "https://t.me/wb_detector_support"),
        proxy_url=os.getenv("PROXY_URL", "").strip(),
    )
