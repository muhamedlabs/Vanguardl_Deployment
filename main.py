import asyncio
import copy
import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from BANNED_FILES import config
from scripts.monitor import Monitor

log = logging.getLogger("main")

# Шаблоны секретов, которые маскируются в любом выводе
PATTERNS = [
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),  # токен Telegram
    re.compile(r"ibssh_[A-Za-z0-9]+"),             # SSH-токен машины
    re.compile(r"Bearer\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
]


class SafeFormatter(logging.Formatter):
    """Маскирует ключи и токены; в терминале не показывает traceback."""

    def __init__(self, fmt: str, secrets: list[str], traceback: bool):
        super().__init__(fmt, datefmt="%H:%M:%S")
        self.secrets = sorted((s for s in secrets if s), key=len, reverse=True)
        self.traceback = traceback

    def format(self, record: logging.LogRecord) -> str:
        if not self.traceback:
            record = copy.copy(record)
            record.exc_info = record.exc_text = None
        text = super().format(record)
        for secret in self.secrets:
            text = text.replace(secret, "***")
        for pattern in PATTERNS:
            text = pattern.sub("***", text)
        return text


def setup_logging(settings: config.Settings) -> None:
    config.LOGS_DIR.mkdir(exist_ok=True)
    secrets = [
        config.DISCORD_TOKEN, config.TELEGRAM_TOKEN, config.GITHUB_TOKEN, config.AI_KEY,
        *(m.user for m in settings.machines),
    ]

    console = logging.StreamHandler()
    console.setFormatter(SafeFormatter("%(asctime)s  %(levelname)-7s %(message)s", secrets, traceback=False))

    file = RotatingFileHandler(config.LOGS_DIR / "bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(SafeFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", secrets, traceback=True))

    logging.basicConfig(level=logging.INFO, handlers=[console, file])
    # библиотеки молчат ниже WARNING: на INFO они пишут лишнее, в том числе токены машин
    for name in ("asyncssh", "aiogram", "disnake", "aiohttp", "asyncio", "openai", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def guarded(name: str, coro) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("%s stopped due to an error (details in logs/bot.log)", name)


async def run(settings: config.Settings) -> None:
    monitor = Monitor(settings)
    bots = []
    discord = None

    if config.DISCORD_TOKEN:
        from discord_bot.client import DiscordBot

        discord = DiscordBot(monitor)
        bots.append(guarded("Discord", discord.start(config.DISCORD_TOKEN)))

    if config.TELEGRAM_TOKEN:
        from telegram_bot.client import TelegramBot

        bots.append(guarded("Telegram", TelegramBot(config.TELEGRAM_TOKEN, monitor).run()))

    if not bots:
        sys.exit("Set DISCORD_TOKEN and/or TELEGRAM_TOKEN in BANNED_FILES/.env")

    loop = asyncio.create_task(monitor.run())
    try:
        await asyncio.gather(*bots)
    finally:
        loop.cancel()
        if discord:
            await discord.close()


if __name__ == "__main__":
    settings = config.load_settings()
    setup_logging(settings)
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        pass
