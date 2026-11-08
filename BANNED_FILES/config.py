import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DIR = Path(__file__).resolve().parent
LOGS_DIR = DIR.parent / "logs"

load_dotenv(DIR / ".env")


def _ids(value: str) -> list[int]:
    return [int(x) for x in value.replace(" ", "").split(",") if x]


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
ALERT_CHANNEL_ID = int(os.getenv("ALERT_CHANNEL_ID") or 0)
TEST_GUILDS = _ids(os.getenv("TEST_GUILDS", ""))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_ALERT_CHAT_ID = int(os.getenv("TELEGRAM_ALERT_CHAT_ID") or 0)

GITHUB_REPO = (
    os.getenv("GITHUB_REPO", "muhamedlabs/Vanguardl_Deployment")
    .strip()
    .removeprefix("https://github.com/")
    .removeprefix("http://github.com/")
    .removesuffix("/")
    .removesuffix(".git")
)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

AI_KEY = (os.getenv("APINEX_API_KEY") or os.getenv("API") or "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.apinex.bond/v1").strip()
AI_MODEL = os.getenv("AI_MODEL", "free/gpt-6-luna").strip()

SITE_URL = os.getenv("SITE_URL", "https://muhamedlabs.pro").strip()
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")


@dataclass
class Machine:
    name: str
    user: str
    bot_cmd: str


@dataclass
class Settings:
    host: str
    port: int
    interval: int
    machines: list[Machine]


def load_settings() -> Settings:
    path = DIR / (os.getenv("MACHINES_CONFIG") or "machines.json")
    if not path.exists():
        sys.exit(f"{path.name} not found. Copy machines.example.json to machines.json")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    machines = []
    for m in data.get("machines", []):
        for key in ("name", "user", "bot_cmd"):
            if not m.get(key):
                sys.exit(f"Machine {m.get('name', '?')} is missing the '{key}' field")
        machines.append(Machine(m["name"], m["user"], m["bot_cmd"]))
    if not machines:
        sys.exit(f"The machines list in {path.name} is empty")

    return Settings(
        host=data.get("host", "ssh.instabox.sh"),
        port=int(data.get("port", 2222)),
        interval=int(data.get("interval", 900)),
        machines=machines,
    )
