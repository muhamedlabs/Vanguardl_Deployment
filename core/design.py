import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from BANNED_FILES import config

NAME = "Muhamed Ads"
CREATOR = "Andriy Muhamed · Muhamed Labs"

PINK = 0xFD1843
WHITE = 0xFFF9FA
BLACK = 0x222222

LINKS = {
    "site": ("Website", "https://muhamedlabs.pro"),
    "rules": ("Rules", "https://law.muhamedlabs.pro"),
    "telegram": ("Telegram", "https://t.me/muhamedlabs"),
    "support": ("Support", "https://t.me/ProManagerss_bot"),
}

ABOUT_BOT = (
    "Monitors the Muhamed Labs servers and website, keeps bots running on the machines "
    "and posts to the channel when something goes wrong."
)

PROJECT_TEXT = (
    "Muhamed Labs is a technology and creative network: programming, YouTube projects, "
    "a hosting panel and rules, all in one place."
)
PROJECT_FIELDS = [
    ("Panel", "Our own panel for running servers and bots: paid periods, automatic shutdown of inactive servers."),
    ("Rules", "Terms, privacy and the rules of every project are collected on the rules website."),
    ("YouTube", "Game Quest, Nanson, ANIME INDUSTRY, KINO INDUSTRY, Strymus: games, music, anime, movies and streams."),
    ("Programming", "Bots, websites and panel extensions that we build ourselves."),
    ("Creative and tech", "Design, content and technical solutions work together as a single network."),
]


@dataclass
class Field:
    name: str
    value: str
    short: bool = False


@dataclass
class Card:
    title: str
    text: str = ""
    fields: list[Field] = field(default_factory=list)
    footer: str = NAME
    buttons: list[tuple[str, str]] = field(default_factory=list)
    color: int = PINK


def now() -> datetime:
    return datetime.now(timezone.utc)


def clock(dt: datetime | None = None) -> str:
    local = (dt or now()).astimezone(ZoneInfo(config.TIMEZONE))
    offset = int(local.utcoffset().total_seconds() // 3600)
    return f"{local:%H:%M} · UTC{offset:+d}"


def ago(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    sec = int((now() - dt).total_seconds())
    if sec < 60:
        return "just now"
    if sec < 3600:
        return f"{sec // 60} min ago"
    if sec < 86400:
        return f"{sec // 3600} h ago"
    return f"{sec // 86400} d ago"


def span(sec: float) -> str:
    d, rest = divmod(int(sec), 86400)
    h, rest = divmod(rest, 3600)
    parts = [f"{d} d" if d else "", f"{h} h" if h else "", f"{rest // 60} min" if rest >= 60 else ""]
    return " ".join([p for p in parts if p][:2]) or "less than a minute"


def uptime_seconds(text: str) -> int:
    units = {"week": 604800, "day": 86400, "hour": 3600, "minute": 60}
    return sum(int(n) * units[u] for n, u in re.findall(r"(\d+)\s+(week|day|hour|minute)", text))


def bar(ok: int, total: int) -> str:
    # ASCII вместо спецсимволов, чтобы везде отображалось одинаково
    return "[" + "#" * ok + "-" * (total - ok) + "]"


def size(used: int, total: int) -> str:
    if total >= 2048:
        return f"{used / 1024:.1f} / {total / 1024:.1f} GB"
    return f"{used} / {total} MB"
