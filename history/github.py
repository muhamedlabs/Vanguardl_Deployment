import time
from dataclasses import dataclass
from datetime import datetime

import aiohttp

from BANNED_FILES import config


@dataclass
class Commit:
    sha: str
    message: str
    author: str
    date: datetime
    url: str


_cache = {"at": 0.0, "data": []}


async def latest(limit: int = 5) -> list[Commit]:
    if _cache["data"] and time.monotonic() - _cache["at"] < 300:
        return _cache["data"]

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "muhamed-ads-bot"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"

    url = f"https://api.github.com/repos/{config.GITHUB_REPO}/commits"
    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.get(url, params={"per_page": limit}) as resp:
            resp.raise_for_status()
            raw = await resp.json()

    data = [
        Commit(
            sha=c["sha"][:7],
            message=c["commit"]["message"].split("\n")[0],
            author=c["commit"]["author"]["name"],
            date=datetime.fromisoformat(c["commit"]["author"]["date"].replace("Z", "+00:00")),
            url=c["html_url"],
        )
        for c in raw[:limit]
    ]
    _cache.update(at=time.monotonic(), data=data)
    return data
