import asyncio
import logging
import shlex
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import aiohttp
import asyncssh

from BANNED_FILES import config
from BANNED_FILES.config import Machine, Settings
from core.design import now, uptime_seconds

log = logging.getLogger(__name__)

TMUX_SESSION = "bot"
ALERT_AFTER = 3
COOLDOWN = 20


@dataclass
class State:
    online: bool | None = None
    restarted: bool = False
    uptime: int = 0
    load: str = ""
    mem: tuple[int, int] | None = None
    disk: tuple[int, int] | None = None
    ms: int = 0
    error: str = ""
    failures: int = 0
    checked: datetime | None = None


@dataclass
class Event:
    kind: str  # down / up / restarted
    what: str  # Server / Site: что именно проверяли
    name: str
    detail: str
    time: datetime


def _pair(text: str) -> tuple[int, int] | None:
    try:
        used, total = text.split("/")
        return int(used), int(total)
    except ValueError:
        return None


class Monitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.machines = {m.name: m for m in settings.machines}
        self.states = {m.name: State() for m in settings.machines}
        self.site = State() if config.SITE_URL else None
        self.site_name = urlparse(config.SITE_URL).hostname or config.SITE_URL
        self.started = now()
        self.on_event = []
        self.on_check = []
        self._lock = asyncio.Lock()
        self._last = 0.0

    @property
    def all_states(self) -> list[State]:
        return [*self.states.values(), *([self.site] if self.site else [])]

    @property
    def machines_online(self) -> int:
        return sum(1 for s in self.states.values() if s.online)

    async def _ssh(self, m: Machine) -> tuple[str, list[str]]:
        start = shlex.quote(m.bot_cmd)
        inner = shlex.quote(m.bot_cmd + "; :  # keepalive_marker")
        remote = (
            'u=$(uptime -p 2>/dev/null || echo "?"); '
            'l=$(cut -d" " -f1 /proc/loadavg 2>/dev/null || echo "?"); '
            "m=$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf \"%d/%d\", (t-a)/1024, t/1024}' /proc/meminfo 2>/dev/null || echo \"?\"); "
            "d=$(df -Pm \"$HOME\" 2>/dev/null | awk 'NR==2{printf \"%d/%d\", $3, $2}' || echo \"?\"); "
            'up="$u|$l|$m|$d"; '
            'if command -v tmux >/dev/null 2>&1; then '
            f"if tmux has-session -t {TMUX_SESSION} 2>/dev/null; "
            'then echo "ALIVE|$up"; '
            f'else tmux new-session -d -s {TMUX_SESSION} {start} && echo "STARTED|$up"; fi; '
            'else '
            'pf="$HOME/.keepalive.pid"; '
            'if [ -f "$pf" ] && grep -qa keepalive_marker "/proc/$(cat "$pf")/cmdline" 2>/dev/null; '
            'then echo "ALIVE|$up"; '
            f'else setsid nohup bash -c {inner} >> "$HOME/keepalive.out" 2>&1 < /dev/null & '
            'echo $! > "$pf"; sleep 1; echo "STARTED|$up"; fi; '
            'fi'
        )
        try:
            async with asyncssh.connect(
                self.settings.host,
                port=self.settings.port,
                username=m.user,
                password=None,
                client_keys=None,
                agent_path=None,
                known_hosts=None,
                config=None,
                connect_timeout=60,
                keepalive_interval=15,
            ) as conn:
                result = await asyncio.wait_for(conn.run(remote, check=False), timeout=180)
        except asyncio.TimeoutError:
            raise RuntimeError("SSH timeout")
        except (asyncssh.Error, OSError) as e:
            raise RuntimeError(str(e)[:200] or type(e).__name__)

        if result.exit_status != 0:
            msg = str(result.stderr or "").strip() or f"ssh exit {result.exit_status}"
            raise RuntimeError(msg[:200])

        status, *parts = str(result.stdout or "").strip().split("|")
        return status, parts

    def _result(self, st: State, what: str, name: str, error: str = "") -> list[Event]:
        events = []
        st.checked = now()
        if error:
            st.failures += 1
            st.online = False
            st.restarted = False
            st.error = error
            if st.failures == ALERT_AFTER:
                events.append(Event("down", what, name, error, st.checked))
        else:
            if st.failures >= ALERT_AFTER:
                events.append(Event("up", what, name, "", st.checked))
            st.online = True
            st.failures = 0
            st.error = ""
        return events

    async def _check_machine(self, m: Machine) -> list[Event]:
        st = self.states[m.name]
        try:
            status, parts = await self._ssh(m)
        except Exception as e:
            # SSH-токен не должен попасть ни в чат, ни в лог
            error = str(e).replace(m.user, "***")
            log.warning("%s: %s", m.name, error)
            return self._result(st, "Server", m.name, error)

        events = self._result(st, "Server", m.name)
        uptime, load, mem, disk = (parts + [""] * 4)[:4]
        st.uptime = uptime_seconds(uptime)
        st.load = load if load != "?" else ""
        st.mem = _pair(mem)
        st.disk = _pair(disk)
        st.restarted = status == "STARTED"
        if st.restarted:
            log.info("%s: bot restarted", m.name)
            events.append(Event("restarted", "Server", m.name, "", st.checked))
        return events

    async def _check_site(self) -> list[Event]:
        st = self.site
        started = time.perf_counter()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(config.SITE_URL) as resp:
                    if resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status}")
        except Exception as e:
            log.warning("%s: %s", self.site_name, e)
            return self._result(st, "Site", self.site_name, str(e) or type(e).__name__)

        st.ms = round((time.perf_counter() - started) * 1000)
        return self._result(st, "Site", self.site_name)

    async def check(self) -> None:
        async with self._lock:
            if time.monotonic() - self._last < COOLDOWN:
                return
            jobs = [self._check_machine(m) for m in self.machines.values()]
            if self.site:
                jobs.append(self._check_site())
            results = await asyncio.gather(*jobs)
            self._last = time.monotonic()

        for event in (e for events in results for e in events):
            await self._notify(self.on_event, event)
        await self._notify(self.on_check)

    async def _notify(self, callbacks, *args) -> None:
        done = await asyncio.gather(*(cb(*args) for cb in callbacks), return_exceptions=True)
        for res in done:
            if isinstance(res, Exception):
                log.error("handler error", exc_info=res)

    async def run(self) -> None:
        while True:
            try:
                await self.check()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("check loop error")
            await asyncio.sleep(self.settings.interval)
