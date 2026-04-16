# Touch Grass Bot

A Telegram bot that watches one group chat and, on a schedule, calls out the
most active member and tells them to go outside.

---

## How it works

1. The bot listens for messages in one specific group.
2. Every 30 minutes it finds who sent the most messages.
3. It posts a funny message mentioning them.
4. The counter resets and the next window begins.
5. If nobody talked, it stays quiet.

---

## Setup

### 1. Create the bot with BotFather

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow the prompts.
3. Copy the bot token it gives you. It will look like:

```text
123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

4. Send `/setprivacy`, choose your bot, and set privacy to `Disable` so the bot
   can read group messages. This is required.

### 2. Get your group chat ID

Method A: `@userinfobot`

1. Add `@userinfobot` to your group temporarily.
2. Copy the group chat ID it prints.
3. Remove the bot if you want.

Method B: Telegram API

1. Add your bot to the group and send any message.
2. Open:

```text
https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
```

3. Find the `chat.id` value in the JSON response.

Group IDs are negative. Supergroup IDs usually look like `-1001234567890`.

### 3. Add the bot to the group

1. Open your group.
2. Add your bot by username.
3. Make sure it can read messages and send messages.

It does not need admin rights unless your group restricts posting to admins.

---

## Running locally

### Prerequisites

- Python 3.11 or higher
- `pip`

### Steps

```bash
git clone https://github.com/your-username/touch-grass-bot.git
cd touch-grass-bot

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env

python main.py
```

Fill in `BOT_TOKEN` and `ALLOWED_CHAT_ID` in `.env` before starting the bot.
The app loads `.env` automatically for local development.

---

## Deploying to Railway with GitHub

This repo is already prepared for Railway:

- `railway.json` sets the start command to `python main.py`
- `.python-version` pins Python to `3.11`
- `.env.example` documents the variables Railway will ask for
- `.gitignore` keeps `.env` out of Git

### 1. Push the repo to GitHub

If this folder is not already a Git repo, run:

```bash
git init
git add .
git commit -m "Prepare Railway deploy"
git branch -M main
git remote add origin https://github.com/your-username/touch-grass-bot.git
git push -u origin main
```

### 2. Create the Railway project

1. Go to [Railway](https://railway.app).
2. Sign in with GitHub.
3. Click `New Project`.
4. Choose `Deploy from GitHub repo`.
5. Select this repository.

Railway will build and deploy automatically whenever you push to the connected
branch.

### 3. Add Railway variables

In the Railway service, open the `Variables` tab and add:

| Variable | Required | Example |
| --- | --- | --- |
| `BOT_TOKEN` | Yes | `123456789:AAF...` |
| `ALLOWED_CHAT_ID` | Yes | `-1001234567890` |
| `TOUCH_GRASS_INTERVAL_MINUTES` | No | `30` |
| `LOG_LEVEL` | No | `INFO` |

Railway may suggest these automatically from `.env.example`.

If you want fresh AI-written reminders instead of only the built-in templates,
the preferred free option is Google Gemini. Add:

| Variable | Required | Example |
| --- | --- | --- |
| `GOOGLE_API_KEY` | For Gemini only | `AIza...` |
| `GOOGLE_MODEL` | No | `gemini-2.5-flash-lite` |
| `AI_REMINDERS_ENABLED` | No | `true` |
| `AI_RECENT_MESSAGES_LIMIT` | No | `20` |

OpenAI is still supported too:

| Variable | Required | Example |
| --- | --- | --- |
| `OPENAI_API_KEY` | For AI only | `sk-...` |
| `OPENAI_MODEL` | No | `gpt-5.4-mini` |
| `AI_MODERATION_ENABLED` | No | `true` |

### 4. Deploy and verify

1. Trigger the deploy if Railway has not already started one.
2. Open the `Logs` tab.
3. Look for startup messages from `main.py`.
4. Send a message in your Telegram group and confirm the bot logs it.

### 5. Do not add a public domain

This bot is a background worker that polls Telegram. It does not need:

- an exposed HTTP port
- a public URL
- a custom domain

If Railway asks about networking, you can leave it alone.

---

## Environment variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `BOT_TOKEN` | Yes | none | Telegram bot token from BotFather |
| `ALLOWED_CHAT_ID` | Yes | none | Numeric ID of the allowed Telegram group |
| `TOUCH_GRASS_INTERVAL_MINUTES` | No | `30` | How often to announce the winner |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `GOOGLE_API_KEY` | No | none | Enables Gemini-generated reminder text |
| `GOOGLE_MODEL` | No | `gemini-2.5-flash-lite` | Gemini model used for reminder text |
| `OPENAI_API_KEY` | No | none | Enables OpenAI-generated reminder text |
| `AI_REMINDERS_ENABLED` | No | auto | Explicitly enable or disable AI reminders |
| `OPENAI_MODEL` | No | `gpt-5.4-mini` | Model used to generate reminder text |
| `AI_MODERATION_ENABLED` | No | `true` | Moderates generated text before posting |
| `AI_RECENT_MESSAGES_LIMIT` | No | `20` | Recent AI outputs kept in memory for deduping |

---

## Customizing the messages

Edit `reminder_templates` in `config.py` to change the bot's tone.

`{mention}` is replaced with either `@username` or a clickable Telegram mention.
`{minutes}` is replaced with your configured reminder interval.

If `GOOGLE_API_KEY` is configured, the bot will use Gemini first. If not, it
can use OpenAI when `OPENAI_API_KEY` is configured. In all cases it falls back
to the built-in templates if AI is disabled, fails, or returns something unsafe
or repetitive.

---

## Troubleshooting

**Bot does not see group messages**

- Make sure privacy mode is disabled with `/setprivacy` in BotFather.
- Remove and re-add the bot after changing privacy mode.

**The bot posts in the wrong group or does not post**

- Double-check `ALLOWED_CHAT_ID`.
- Set `LOG_LEVEL=DEBUG` and inspect the logs while sending test messages.

**Railway deployment fails**

- Confirm `requirements.txt` is in the repo root.
- Check Railway build logs for pip install errors.
- Make sure Railway picked up `.python-version` and is building with Python 3.11.

**The bot stops on Railway**

- Check the service logs to see whether it crashed or restarted.
- If your Railway trial or free credits are exhausted, the service will stop
  until you add credits or upgrade your plan.

**Unauthorized errors**

- Your `BOT_TOKEN` is wrong or revoked. Regenerate it with `/revoke` in BotFather.

**AI reminders do not appear**

- Confirm `GOOGLE_API_KEY` or `OPENAI_API_KEY` is set in Railway.
- Gemini is preferred when `GOOGLE_API_KEY` is present. The default Gemini model
  is `gemini-2.5-flash-lite`, which is currently listed on Google's free tier.
- Confirm `OPENAI_API_KEY` is set in Railway.
- If your account does not have access to `gpt-5.4-mini`, change `OPENAI_MODEL`
  to another model available on your OpenAI account.
- Check Railway logs. The bot will fall back to built-in templates when OpenAI
  generation or moderation fails.

---

## Project structure

```text
touch-grass-bot/
|-- main.py
|-- config.py
|-- counter.py
|-- handlers.py
|-- ai_reminders.py
|-- scheduler.py
|-- requirements.txt
|-- Procfile
|-- railway.json
|-- .python-version
|-- .gitignore
|-- .env.example
`-- README.md
```

---

## Railway notes

- Railway uses ephemeral storage by default, which is fine for this bot.
- The bot stores counters in memory only, so a restart resets the current
  counting window.
- For always-on uptime, a paid Railway plan is safer than relying on trial or
  free credits.
