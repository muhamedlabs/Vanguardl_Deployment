# Vanguardl Deployment <a href="README.md"><img src="https://github.com/muhamedlabs/MuhamedTrash/blob/main/Flags/Russia_flag.png?raw=true" alt="RU" width="28" height="28" style="border-radius: 12px;"></a> <a href="README_UA.md"><img src="https://github.com/muhamedlabs/MuhamedTrash/blob/main/Flags/Ukraine_flag.png?raw=true" alt="UA" width="28" height="28" style="border-radius: 12px;"></a> <a href="README_EN.md"><img src="https://github.com/muhamedlabs/MuhamedTrash/blob/main/Flags/Unit_King_flag.png?raw=true" alt="UK" width="28" height="28" style="border-radius: 12px;"></a>

<img width="1920" height="957" alt="image" src="https://github.com/user-attachments/assets/d90e56fb-5739-4f6b-a5bd-4a0aed94236a" />

## Description

**Vanguardl Deployment** is a monitoring bot for Discord and Telegram. It watches the Muhamed Abs servers and website, keeps the bots running on the machines and posts to the alert channel when something goes wrong.

Suitable for:

* monitoring servers behind a hosting panel
* keeping bots alive on machines that stop when inactive
* status alerts in a Discord channel or a Telegram chat

One process runs both bots and a single monitoring loop. No database is needed: the state is kept in memory.

---

## Features

* Works in Discord and Telegram at the same time (either one can be disabled)
* Checks every machine over SSH: uptime, load, memory and disk
* Starts the bot command on a machine if it is not running (tmux, with a fallback without it)
* Website check with response time
* Alerts when a server or the site goes down, comes back, or the bot was restarted
* An alert is sent only after several failed checks in a row, so a single glitch does not trigger it
* `/ai` command for questions to any OpenAI-compatible API
* `/history` command with the latest GitHub commits
* Discord status shows how many machines are online
* Minimal terminal output: no keys, tokens or tracebacks, and secrets are masked in the log file too

---

## Commands

| Command    | What it does                                           |
| ---------- | ------------------------------------------------------ |
| `/start`   | about the bot, ping, creator and the command list      |
| `/info`    | detailed status of machines and the website            |
| `/check`   | run a check right now and wake up the servers          |
| `/project` | about the Muhamed Ads project                          |
| `/history` | latest commits from GitHub                             |
| `/ai`      | ask the AI a question, for example `/ai What is Pterodactyl?` |

In Discord these are slash commands (guild only). In Telegram they work in chats and in channels.

---

## How it works

1. Every `interval` seconds (15 minutes by default) the monitor connects to each machine over SSH
2. On the machine it collects uptime, load, memory and disk usage
3. If the bot session is missing, it starts `bot_cmd` in a tmux session named `bot` (or in the background if tmux is not installed)
4. It also requests `SITE_URL` and measures the response time
5. After 3 failed checks in a row an alert is sent, and when the target recovers a recovery alert follows
6. The `/check` command triggers the same check manually, with a 20 second cooldown between checks

---

## Project structure

```text
Muhamed_Ads/
├── main.py                  # entry point, logging, start of both bots
├── requirements.txt
├── README.md                # documentation (RU)
├── README_UA.md             # documentation (UA)
├── README_EN.md             # documentation (EN)
├── BANNED_FILES/
│   ├── config.py            # settings loader
│   ├── .env                 # secrets (not in git)
│   ├── machines.json        # machines list (not in git)
│   └── machines.example.json
├── core/
│   ├── commands.py          # commands, cards and alerts, shared by both bots
│   └── design.py            # name, links, colors, time formatting
├── discord_bot/
│   └── client.py            # Discord client (disnake)
├── telegram_bot/
│   └── client.py            # Telegram client (aiogram)
├── history/
│   └── github.py            # latest commits (cached for 5 minutes)
└── scripts/
    └── monitor.py           # SSH and website checks, events
```

---

## Installation

Python 3.10 or newer is required.

1. Clone the repository and install the dependencies:

```bash
pip install -r requirements.txt
```

2. Create `BANNED_FILES/.env` with your settings (see below)
3. Copy `BANNED_FILES/machines.example.json` to `BANNED_FILES/machines.json` and fill in your machines
4. Run the bot:

```bash
python main.py
```

At least one of `DISCORD_TOKEN` and `TELEGRAM_TOKEN` must be set.

---

## Configuration

### Environment variables

Set them in `BANNED_FILES/.env`:

| Variable                 | Purpose                                                          |
| ------------------------ | ---------------------------------------------------------------- |
| `DISCORD_TOKEN`          | Discord bot token (Discord is off if empty)                      |
| `ALERT_CHANNEL_ID`       | Discord channel for alerts                                       |
| `TEST_GUILDS`            | server ids, comma separated; slash commands appear there instantly |
| `TELEGRAM_TOKEN`         | Telegram bot token (Telegram is off if empty)                    |
| `TELEGRAM_ALERT_CHAT_ID` | Telegram chat or channel for alerts                              |
| `GITHUB_REPO`            | repository for `/history`, as `owner/name` or a full URL         |
| `GITHUB_TOKEN`           | optional, raises the GitHub API rate limit                       |
| `APINEX_API_KEY`         | key for `/ai` (the `API` variable also works)                    |
| `AI_BASE_URL`            | OpenAI-compatible API address                                    |
| `AI_MODEL`               | model name                                                       |
| `SITE_URL`               | website to check (the check is skipped if empty)                 |
| `TIMEZONE`               | time zone for the clock, default `Europe/Kyiv`                   |
| `MACHINES_CONFIG`        | machines file name, default `machines.json`                      |

### Machines

`BANNED_FILES/machines.json`:

```json
{
  "host": "ssh.instabox.sh",
  "port": 2222,
  "interval": 900,
  "machines": [
    {
      "name": "machine1",
      "user": "YOUR_SSH_USER",
      "bot_cmd": "while true; do date >> ~/keepalive.log; sleep 60; done"
    }
  ]
}
```

| Field     | Purpose                                                     |
| --------- | ----------------------------------------------------------- |
| `host`    | SSH host                                                    |
| `port`    | SSH port                                                    |
| `interval`| time between automatic checks, in seconds                   |
| `name`    | machine name shown in cards and alerts                      |
| `user`    | SSH user of the machine                                     |
| `bot_cmd` | command that is started on the machine if it is not running |

Connection is made without a password and without keys: the `user` value works as the credential, so keep this file private.

### Alerts

* **Server is down / Site is down** is sent after 3 failed checks in a row
* **Back online** is sent when the target responds again after such an outage
* **Bot restarted** is sent when the bot had to be started again on a machine

---

## Security

* `BANNED_FILES/.env` and `BANNED_FILES/machines.json` are listed in `.gitignore`, never commit them
* Tokens, API keys and SSH users are replaced with `***` in the terminal and in `logs/bot.log`
* The terminal shows short status lines only. Full tracebacks go to `logs/bot.log` (rotated, up to 1 MB per file, 3 backups)
* Libraries are silenced below the WARNING level, so they cannot print anything extra

---

## Technologies

* **Python 3.10+**, asyncio
* **disnake** - Discord
* **aiogram 3** - Telegram
* **asyncssh** - machine checks
* **aiohttp** - website and GitHub requests
* **openai** - client for the AI command
* **python-dotenv** - settings

---

## FAQ

**The bot does not start.**
Check that `DISCORD_TOKEN` or `TELEGRAM_TOKEN` is set in `BANNED_FILES/.env` and that `machines.json` exists and contains at least one machine.

**Slash commands do not appear in Discord.**
Global commands can take a while to show up. Put your server id into `TEST_GUILDS` to get them immediately.

**There are no alerts.**
Check `ALERT_CHANNEL_ID` and `TELEGRAM_ALERT_CHAT_ID`, and make sure the bot can write to that channel or chat. Alerts are sent only after 3 failed checks in a row.

**Why is the terminal almost empty?**
This is intended. Details are in `logs/bot.log`.

**Can I run only one of the bots?**
Yes. Leave the other token empty.

---

## Contributing

Ideas and improvements are welcome:

1. Fork the repository
2. Create a branch for your changes
3. Open a Pull Request with a short description

Report bugs via an Issue: include the steps to reproduce.

---

## Contact and support

We are always open to communication, new ideas and collaboration. For any questions, contact us:

- Telegram channel: https://t.me/muhamedlabs
- Email: partners@muhamedlabs.pro
- Discord: https://discord.com/users/768782555171782667

<br>

<div align="center">
  <sub><img src="https://github.com/muhamedlabs/MuhamedTrash/raw/main/Avatars/Muhamed_IT.png" width="20" style="vertical-align: middle;"> 2023-2028 Muhamed IT <img src="https://github.com/muhamedlabs/MuhamedTrash/raw/main/Avatars/Muhamed_IT.png" width="20" style="vertical-align: middle;"> </sub>
</div>