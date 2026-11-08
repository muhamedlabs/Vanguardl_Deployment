import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from openai import AsyncOpenAI

from BANNED_FILES import config
from history import github
from core.design import (
    ABOUT_BOT, CREATOR, LINKS, NAME, PROJECT_FIELDS, PROJECT_TEXT, WHITE,
    Card, Field, ago, bar, clock, size, span,
)
from scripts.monitor import Event, Monitor, State


log = logging.getLogger(__name__)

AI_SYSTEM = (
    "You are the assistant of the Muhamed Ads bot. Answer briefly and to the point "
    "in the user's language, without extra formatting, in no more than 1500 characters."
)
_ai = None
_ai_slots = asyncio.Semaphore(3)  # не больше 3 одновременных запросов к ИИ


@dataclass
class Ctx:
    monitor: Monitor
    ping: Callable[[], Awaitable[int]]
    args: str = ""


@dataclass
class Command:
    name: str
    description: str
    run: Callable[[Ctx], Awaitable[Card]]
    slow: bool = False
    arg: str = ""


def _error(text: str) -> str:
    return f"`{text.replace(chr(96), chr(39))[:120]}`"


def _machine(name: str, st: State) -> tuple[str, str]:
    if st.online is None:
        return name, "Status: pending\nNot checked yet"
    if not st.online:
        return name, "\n".join([
            "Status: offline",
            f"Reason: {_error(st.error)}",
            f"Checked: {ago(st.checked)}",
        ])

    lines = [
        "Status: online",
        "Bot: restarted just now" if st.restarted else "Bot: running",
        f"Uptime: {span(st.uptime)}",
    ]
    if st.load:
        lines.append(f"Load: {st.load}")
    if st.mem:
        lines.append(f"Memory: {size(*st.mem)}")
    if st.disk:
        lines.append(f"Disk: {size(*st.disk)}")
    lines.append(f"Checked: {ago(st.checked)}")
    return name, "\n".join(lines)


def _site(name: str, st: State) -> tuple[str, str]:
    if st.online is None:
        return name, "Status: pending\nNot checked yet"
    if not st.online:
        return name, f"Status: offline\nReason: {_error(st.error)}\nChecked: {ago(st.checked)}"
    return name, f"Status: online\nResponse: {st.ms} ms\nChecked: {ago(st.checked)}"


def _report(ctx: Ctx, title: str) -> Card:
    mon = ctx.monitor
    states = mon.all_states
    known = [s for s in states if s.online is not None]
    ok = sum(1 for s in known if s.online)

    if not known:
        head = "First check is still running"
    elif ok == len(states):
        head = "Everything is working"
    elif ok == 0:
        head = "Nothing is responding"
    else:
        head = "Some problems detected"

    fields = [Field(*_machine(name, st)) for name, st in mon.states.items()]
    if mon.site:
        fields.append(Field(*_site(mon.site_name, mon.site)))
    fields.append(Field("Time", clock(), True))

    return Card(
        title=title,
        text=f"**{head}**\n`{bar(ok, len(states))}`  {ok} of {len(states)}",
        fields=fields,
        footer=f"Auto-check every {mon.settings.interval // 60} min · {NAME}",
    )


async def start(ctx: Ctx) -> Card:
    menu = "\n".join(f"/{c.name} - {c.description}" for c in COMMANDS)
    return Card(
        title=f"{NAME} · bot",
        text=ABOUT_BOT,
        fields=[
            Field("Ping", f"{await ctx.ping()} ms", True),
            Field("Creator", CREATOR, True),
            Field("Commands", menu),
        ],
        buttons=[LINKS["site"], LINKS["telegram"]],
    )


async def info(ctx: Ctx) -> Card:
    return _report(ctx, "Server status")


async def check(ctx: Ctx) -> Card:
    await ctx.monitor.check()
    return _report(ctx, "Check complete")


async def project(ctx: Ctx) -> Card:
    return Card(
        title=NAME,
        text=PROJECT_TEXT,
        fields=[Field(name, value) for name, value in PROJECT_FIELDS],
        buttons=[LINKS["site"], LINKS["rules"], LINKS["telegram"]],
    )


async def history(ctx: Ctx) -> Card:
    repo = config.GITHUB_REPO
    if not repo:
        return Card(title="Change history", text="The repository is not set in the settings yet.")

    try:
        commits = await github.latest(5)
    except Exception:
        return Card(title="Change history", text="GitHub is not responding right now. Try again later.")

    return Card(
        title="Latest commits",
        text=f"**{repo}**",
        fields=[
            Field(c.message[:80], f"[{c.sha}]({c.url}) · {c.author} · {ago(c.date)}")
            for c in commits
        ],
        buttons=[("GitHub", f"https://github.com/{repo}/commits")],
    )


async def ask_ai(question: str) -> str:
    global _ai
    if _ai is None:
        _ai = AsyncOpenAI(api_key=config.AI_KEY, base_url=config.AI_BASE_URL, timeout=60)

    async with _ai_slots:
        res = await _ai.chat.completions.create(
            model=config.AI_MODEL,
            messages=[
                {"role": "system", "content": AI_SYSTEM},
                {"role": "user", "content": question[:1000]},
            ],
            max_tokens=700,
        )
    return (res.choices[0].message.content or "").strip()


async def ai(ctx: Ctx) -> Card:
    question = ctx.args.strip()
    if not question:
        return Card(title="AI", text="Write your question after the command, for example:\n`/ai What is Pterodactyl?`")
    if not config.AI_KEY:
        return Card(title="AI", text="The APInex key is not set in the settings yet.")

    try:
        answer = await ask_ai(question)
    except Exception:
        log.exception("AI error")
        return Card(title="AI", text="The AI is not responding right now. Try again later.")

    if len(answer) > 3000:
        answer = answer[:3000].rstrip() + "..."
    return Card(
        title="AI answer",
        text=answer or "Empty answer, try rephrasing.",
        fields=[Field("Question", question[:200])],
        footer=f"{config.AI_MODEL} · {NAME}",
    )


def alert(e: Event) -> Card:
    fields = [Field(e.what, e.name, True), Field("Time", clock(e.time), True)]

    if e.kind == "down":
        fields.append(Field("Reason", f"`{e.detail.replace('`', chr(39))[:200]}`"))
        return Card(
            title=f"{e.what} is down",
            text=f"**{e.name}** has not responded for several checks in a row.",
            fields=fields,
        )
    if e.kind == "up":
        return Card(
            title=f"{e.what} is back online",
            text=f"**{e.name}** is reachable again.",
            fields=fields,
            color=WHITE,
        )
    return Card(
        title="Bot restarted",
        text=f"The bot was started again on **{e.name}**: the machine woke up or there was no session.",
        fields=fields,
    )


COMMANDS = [
    Command("start", "about the bot", start),
    Command("info", "detailed status of machines and website", info),
    Command("project", "about the Muhamed Ads project", project),
    Command("history", "latest commits from GitHub", history, slow=True),
    Command("ai", "ask the AI", ai, slow=True, arg="Your question"),
    Command("check", "check and wake up the servers", check, slow=True),
]
