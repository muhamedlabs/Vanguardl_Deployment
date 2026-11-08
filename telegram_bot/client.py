import asyncio
import html
import logging
import re
import time
from dataclasses import replace

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command as TgCommand
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message

from BANNED_FILES import config
from core.commands import COMMANDS, Command, Ctx, alert
from core.design import Card
from scripts.monitor import Event, Monitor

log = logging.getLogger(__name__)


def md(text: str) -> str:
    text = html.escape(text, quote=False)
    blocks = []

    def keep(m):
        blocks.append(f"<pre>{m.group(1).strip()}</pre>")
        return f"\x00{len(blocks) - 1}\x00"

    text = re.sub(r"```\w*\n?(.*?)```", keep, text, flags=re.S)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: blocks[int(m.group(1))], text)


def render(card: Card) -> tuple[str, InlineKeyboardMarkup | None]:
    blocks = [f"<b>{md(card.title)}</b>" + (f"\n{md(card.text)}" if card.text else "")]
    short = []
    for f in card.fields:
        if f.short:
            short.append(f"<b>{md(f.name)}</b>  {md(f.value)}")
            continue
        if short:
            blocks.append("\n".join(short))
            short = []
        blocks.append(f"<b>{md(f.name)}</b>\n{md(f.value)}")
    if short:
        blocks.append("\n".join(short))
    blocks.append(f"<i>{md(card.footer)}</i>")

    markup = None
    if card.buttons:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=label, url=url) for label, url in card.buttons]]
        )
    return "\n\n".join(blocks), markup


class TelegramBot:
    def __init__(self, token: str, monitor: Monitor):
        self.bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
        )
        self.dp = Dispatcher()
        self.ctx = Ctx(monitor, self._ping)

        router = Router()
        for cmd in COMMANDS:
            handler = self._handler(cmd)
            router.message.register(handler, TgCommand(cmd.name))
            router.channel_post.register(handler, TgCommand(cmd.name))
        self.dp.include_router(router)
        monitor.on_event.append(self.send_alert)

    async def _ping(self) -> int:
        started = time.perf_counter()
        await self.bot.get_me()
        return round((time.perf_counter() - started) * 1000)

    def _handler(self, cmd: Command):
        async def handle(message: Message):
            wait = await message.answer("Please wait...") if cmd.slow else None
            ctx = replace(self.ctx, args=(message.text or "").partition(" ")[2].strip())
            try:
                text, markup = render(await cmd.run(ctx))
            except Exception:
                log.exception("error in /%s", cmd.name)
                text, markup = "Something went wrong. Try again later.", None
            if wait:
                await wait.edit_text(text, reply_markup=markup)
            else:
                await message.answer(text, reply_markup=markup)

        return handle

    async def send_alert(self, event: Event) -> None:
        if not config.TELEGRAM_ALERT_CHAT_ID:
            return
        text, markup = render(alert(event))
        try:
            await self.bot.send_message(config.TELEGRAM_ALERT_CHAT_ID, text, reply_markup=markup)
        except TelegramAPIError:
            log.exception("Failed to send alert to Telegram")

    async def run(self) -> None:
        try:
            me = await self.bot.get_me()
            log.info("Telegram ready: @%s", me.username)
            await self.bot.set_my_commands(
                [BotCommand(command=c.name, description=c.description) for c in COMMANDS]
            )
            await self.dp.start_polling(self.bot, handle_signals=False)
        except asyncio.CancelledError:
            raise
        finally:
            await self.bot.session.close()
