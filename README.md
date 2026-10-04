# CashBackBuddy

Personal, read-only Telegram bot for choosing a US credit card by spending category.

Send `grocery`, `groceries`, `restaurant`, `dining`, `entertainment`, or `shopping` to get your cards ranked by published cashback rate. Matching ignores case and surrounding whitespace. `/start` and `/help` explain usage; `/categories` lists choices. Only the configured user's private chat receives replies, including help.

The initial `cards.yaml` has no cards, so a supported query returns `No cards configured yet.` No bank connections, transaction tracking, points valuation, or Telegram editing are included.

## Local setup

Use Python 3.12 or newer. From this repository, on PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN = "your_botfather_token"
$env:TELEGRAM_ALLOWED_USER_ID = "your_numeric_user_id"
.venv\Scripts\python bot.py
```

On Linux/macOS, use `.venv/bin/python` and `export TELEGRAM_BOT_TOKEN='...'` / `export TELEGRAM_ALLOWED_USER_ID='...'`. Stop with Ctrl+C. Local Python does **not** automatically read `.env`; set the environment variables explicitly. Do not paste tokens into logs, screenshots, or Git.

Create the bot through Telegram's official `@BotFather`. Obtain your **user** ID, not the bot's ID or a group's ID, from an ID lookup you trust. Alternatively, send your new bot a private message and inspect the Telegram Bot API `getUpdates` response's `message.from.id` on your own machine before polling starts. Never share the request URL: it contains your token. Set that positive numeric ID as `TELEGRAM_ALLOWED_USER_ID`.

Missing environment variables or invalid YAML stop startup with an actionable error. Unexpected queries log a traceback with token redaction and receive a short failure reply only in the owner's private chat.

## Card data

Edit `cards.yaml` locally. Keep the configured categories and replace `cards: []` with your own data. This fictional example illustrates the schema, not current offers:

```yaml
timezone: America/New_York
categories:
  grocery:
    aliases: [groceries, supermarket, supermarkets]
  restaurant:
    aliases: [restaurants, dining]
  entertainment:
    aliases: []
  shopping:
    aliases: []
cards:
  - id: example_card
    name: Example Card
    base_cashback_percent: 1
    rewards:
      - category: restaurant
        cashback_percent: 3
        conditions:
          - Eligible dining purchases only.
      - category: grocery
        cashback_percent: 5
        starts_on: "2026-10-01"
        ends_on: "2026-12-31"
        conditions:
          - Activation required.
          - $1,500 combined quarterly spending cap.
          - Excludes warehouse clubs.
    benefits:
      - name: Purchase protection
        categories: [shopping]
        description: Coverage subject to the card's terms.
```

- Required: `timezone`, nonempty `categories`, `cards`; each card needs a unique nonempty `id`, `name`, and nonnegative finite `base_cashback_percent`.
- `rewards`, `benefits`, and `conditions` default to empty lists. Rates are **total percentages**, not additions to base. Reward categories reference canonical category keys, not aliases.
- Omit both dates for ongoing rewards; otherwise supply both ISO dates. Boundaries are inclusive. Future/expired offers do not apply; the highest active rate or base rate wins.
- All equal winning offers are displayed separately with all conditions; they are not stackable. All cards appear, ordered by descending rate, then name, then ID.
- Benefit `categories: []` (or omitted) means every category; benefits never affect ranking.
- Use a valid IANA timezone. Rules are evaluated in that timezone on **each query**, so date transitions need no restart. Windows timezone data is installed through `tzdata`.
- Data loads once at startup: restart after editing. Invalid types, dates, references, duplicate YAML keys, alias collisions, and boolean/negative/nonfinite rates are rejected. YAML merges that override keys are also rejected; use explicit unique fields.

Rankings do not account for exhausted caps, activation status, or merchant-specific eligibility. They show conditional published rates for you to assess, not guaranteed earnings. Review issuer terms. Keep real card details private; do not commit them to a public repository.

## Homelab: Docker Compose

Install Docker with Compose. Copy `.env.example` to `.env` and replace both placeholders locally. `.env` is excluded from Git and the image build. Compose reads it automatically; required-variable checks prevent starting with missing values.

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose logs -f
docker compose restart
docker compose down
```

Use `docker compose restart` after editing the host `cards.yaml`; rebuilding is unnecessary. The YAML mount is read-only inside the container. One Python 3.12 container polls Telegram, restarts unless stopped, and needs outbound HTTPS but no inbound ports or database. Run only one polling instance for the token; stop the local bot before deploying.

## Verification

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -c "from rewards import load_cards; load_cards('cards.yaml'); print('YAML valid')"
```

For live acceptance, with your own credentials: test `/help` and a category privately, verify another user and a group get no replies, and use temporary fictional rules to check expired-rate fallback and reload after an edit/restart. Restore the initial empty file afterward if real data is not ready. Offline tests do not replace this live check.

Implementation verification: 15 offline tests passed on Python 3.14.7. Docker CLI was unavailable, so Compose validation/build and Python 3.12 container execution were not verified. Live Telegram checks were not run because credentials were not supplied.

[Approved design](docs/superpowers/specs/2026-10-04-cashback-bot-design.md) · [Implementation plan](docs/superpowers/plans/2026-10-04-cashback-bot.md)
