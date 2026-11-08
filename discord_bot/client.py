import asyncio
import logging
import math
from dataclasses import replace

import disnake
from disnake.ext import commands

from BANNED_FILES import config
from core.commands import COMMANDS, Command, Ctx, alert
from core.design import NAME, Card
from scripts.monitor import Event, Monitor

log = logging.getLogger(__name__)


def render(card: Card) -> dict:
    embed = disnake.Embed(title=card.title, description=card.text or None, color=card.color)
    embed.set_author(name=NAME)
    for f in card.fields:
        embed.add_field(name=f.name, value=f.value, inline=f.short)
    embed.set_footer(text=card.footer)

    out = {"embed": embed}
    if card.buttons:
        view = disnake.ui.View(timeout=None)
        for label, url in card.buttons:
            view.add_item(disnake.ui.Button(label=label, url=url))
        out["view"] = view
    return out


class DiscordBot(commands.InteractionBot):
    def __init__(self, monitor: Monitor):
        super().__init__(intents=disnake.Intents.default(), test_guilds=config.TEST_GUILDS or None)
        self.monitor = monitor
        self.ctx = Ctx(monitor, self._ping)

        monitor.on_event.append(self.send_alert)
        monitor.on_check.append(self.update_presence)
        for cmd in COMMANDS:
            self._register(cmd)

    async def _ping(self) -> int:
        return round(self.latency * 1000) if math.isfinite(self.latency) else 0

    async def _answer(self, inter: disnake.ApplicationCommandInteraction, cmd: Command, args: str = "") -> None:
        ctx = replace(self.ctx, args=args)
        if cmd.slow:
            await inter.response.defer()
            await inter.edit_original_response(**render(await cmd.run(ctx)))
        else:
            await inter.response.send_message(**render(await cmd.run(ctx)))

    def _register(self, cmd: Command) -> None:
        options = dict(name=cmd.name, description=cmd.description, contexts=disnake.InteractionContextTypes(guild=True))
        if cmd.arg:
            @self.slash_command(**options)
            async def with_arg(
                inter: disnake.ApplicationCommandInteraction,
                question: str = commands.Param(name="question", description=cmd.arg, max_length=500),
            ):
                await self._answer(inter, cmd, question)
        else:
            @self.slash_command(**options)
            async def plain(inter: disnake.ApplicationCommandInteraction):
                await self._answer(inter, cmd)

    async def update_presence(self) -> None:
        if not self.is_ready():
            return
        mon = self.monitor
        await self.change_presence(
            activity=disnake.Activity(
                type=disnake.ActivityType.watching,
                name=f"Instabox {mon.machines_online}/{len(mon.machines)}",
            )
        )

    async def send_alert(self, event: Event) -> None:
        if not config.ALERT_CHANNEL_ID:
            return
        try:
            await asyncio.wait_for(self.wait_until_ready(), timeout=60)
        except asyncio.TimeoutError:
            log.warning("Discord not ready, alert skipped")
            return

        channel = self.get_channel(config.ALERT_CHANNEL_ID)
        if channel is None:
            log.warning("Channel %s not found", config.ALERT_CHANNEL_ID)
            return
        try:
            await channel.send(**render(alert(event)))
        except disnake.HTTPException:
            log.exception("Failed to send alert to Discord")

    async def on_ready(self):
        log.info("Discord ready: %s", self.user)
        await self.update_presence()

    async def on_slash_command_error(self, inter, error):
        log.error("error in /%s", inter.data.name, exc_info=error)
        text = "Something went wrong. Try again later."
        if inter.response.is_done():
            await inter.followup.send(text, ephemeral=True)
        else:
            await inter.response.send_message(text, ephemeral=True)
