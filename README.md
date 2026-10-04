# CashBackBuddy

Personal, read-only Telegram bot for choosing a US credit card by spending category.

Send `grocery`, `groceries`, `restaurant`, `dining`, `entertainment`, or `shopping` to get your cards ranked by published cashback rate. Matching ignores case and surrounding whitespace. `/start` and `/help` explain usage; `/categories` lists choices. Only the configured user's private chat receives replies, including help.

The initial `cards.yaml` has no cards, so a supported query returns `No cards configured yet.` No bank connections, transaction tracking, points valuation, or Telegram editing are included.

## Run with Docker Compose

The included [compose.yaml](compose.yaml) builds the image from [Dockerfile](Dockerfile). No separate manual image build is needed.

1. Copy `.env.example` to `.env`:

   ```sh
   cp .env.example .env
   ```

2. Set `TELEGRAM_BOT_TOKEN` from `@BotFather` and `TELEGRAM_ALLOWED_USER_ID` to your positive numeric Telegram **user** ID in `.env`. Keep this file private; it is excluded from Git and the image.

3. Build and start:

   ```sh
   docker compose up -d --build
   ```

View logs with `docker compose logs -f`. Stop with `docker compose down`. Run only one polling instance per bot token.

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
- Use a valid IANA timezone. Rules are evaluated in that timezone on **each query**, so date transitions need no restart.
- Data loads once at startup: restart after editing. Invalid types, dates, references, duplicate YAML keys, alias collisions, and boolean/negative/nonfinite rates are rejected. YAML merges that override keys are also rejected; use explicit unique fields.

Rankings do not account for exhausted caps, activation status, or merchant-specific eligibility. They show conditional published rates for you to assess, not guaranteed earnings. Review issuer terms. Keep real card details private; do not commit them to a public repository.

After editing the host `cards.yaml`, run `docker compose restart` to reload it. No rebuild is needed; the file is mounted read-only in the container.

## Local development

Use Python 3.12 or newer:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

To run without Docker, export `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID`, then run `.venv/bin/python bot.py`. Python does not automatically load `.env`. On Windows, use `.venv\Scripts\python` instead.
