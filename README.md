# CashBackBuddy

Personal, read-only Telegram bot for choosing a US credit card by spending category.

Send `grocery`, `groceries`, `restaurant`, `dining`, `entertainment`, or `shopping` to get an emoji-led ranking of your top three cards. Matching ignores case and surrounding whitespace. Only configured users' private chats receive replies, including help.

The initial `cards.yaml` has no cards, so a supported query returns `💳 No cards configured yet.` No bank connections, transaction tracking, or Telegram editing are included.

Example reply (illustrative rates):

```text
🍽 Dining

🥇 Chase Sapphire Preferred — 3x Chase points ≈ 3%
🥈 Example Cashback Card — 2%
🥉 Example Base Card — 1%

Best choice: Chase Sapphire Preferred

🧮 Chase points valued at 1¢ each via Sapphire Preferred’s Chase Travel portal.
```

Tied highest returns show `Best choices`, including winners outside the top three. Full conditions and benefits are available through `/card`, not repeated in category replies.

## Bot commands

| Command | Response |
| --- | --- |
| `/start` | Show a short usage example and commands, without the category list. |
| `/help` | Show the same help as `/start`. |
| `/categories` | List the main spending categories configured in `cards.yaml`. |
| `/cards` | List your cards and their detail commands. |
| `/card <name or ID>` | Full rewards, dates, conditions, benefits, and valuation assumptions. |

Card lookup ignores case. Exact IDs take priority, then exact names; a partial name works if it identifies just one card. Ambiguous matches list choices instead of selecting one. Card IDs must be unique ignoring case.

Category labels use meaningful emojis where available; unfamiliar categories use plain text rather than a generic tag emoji.

Walmart and Target are separate categories, not grocery aliases. Their purchases use base rates unless an explicit merchant reward is configured; grocery and online-shopping bonuses are not inherited automatically.

The main list omits Red Cross, T-Mobile Dining, and issuer-specific portal categories. `travel`, `chase_travel`, and `capital_one_travel` queries open one travel overview: your preferred card first, direct-booking and portal rates shown separately, plus relevant protections and portal alternatives with their conditions. Portal alternatives require an active explicit portal rule; base-rate cards do not fill a podium. `capital_one_entertainment` remains a separate qualified query. Portal reward rules remain distinct internally so their rates never apply to ordinary spending.

Set the optional top-level `preferred_travel_card` in your `cards.yaml` to a configured card ID, for example `preferred_travel_card: chase_sapphire_preferred`. It is a personal preference, not a claim of the highest reward rate. The card must exist; invalid references prevent startup. Without this setting, travel shows direct-booking rates and portal options without inventing a preference. Rates, conditions, and benefits come from your saved data; add Sapphire Preferred using the Chase points schema below, not cashback percentages.

For recommendations, send a category or alias as plain text, such as `grocery` or `dining`—not `/grocery`. Unknown slash commands are ignored.

All commands and category queries work only in configured users' private chats. Other users and group chats receive no replies. All allowed users share the same card data.

## Run with Docker Compose

The included [compose.yaml](compose.yaml) builds the image from [Dockerfile](Dockerfile). No separate manual image build is needed.

1. Copy `.env.example` to `.env`:

   ```sh
   cp .env.example .env
   ```

2. Set `TELEGRAM_BOT_TOKEN` from `@BotFather` and `TELEGRAM_ALLOWED_USER_ID` to one or more positive numeric Telegram **user** IDs in `.env`, for example `TELEGRAM_ALLOWED_USER_ID=123456789,987654321`. A single ID still works; whitespace around IDs is ignored and duplicates are removed. Empty entries and invalid IDs prevent startup. Keep this file private; it is excluded from Git and the image.

3. Build and start:

   ```sh
   docker compose up -d --build
   ```

View logs with `docker compose logs -f`. Stop with `docker compose down`. Run only one polling instance per bot token.

After changing `.env`, run `docker compose up -d` to recreate the container with the new environment; `docker compose restart` does not reload it.

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

- Required: `timezone`, nonempty `categories`, `cards`; each card needs a unique nonempty `id`, `name`, and nonnegative finite base rate (`base_cashback_percent` or the Chase points fields below).
- `rewards`, `benefits`, and `conditions` default to empty lists. Rates are **total percentages**, not additions to base. Reward categories reference canonical category keys, not aliases.
- Omit both dates for ongoing rewards; otherwise supply both ISO dates. Boundaries are inclusive. Future/expired offers do not apply; the highest active rate or base rate wins.
- The top three cards appear, ordered by descending cashback-equivalent return. Equal rates preserve the order of entries in the YAML `cards` list: put preferred cards first to control ties (for example, Wells Fargo before T-Mobile). Full card details show all configured offers and conditions, including future/expired offers with their dates; they are not stackable.
- Benefit `categories: []` (or omitted) means every category; benefits never affect ranking.
- Use a valid IANA timezone. Rules are evaluated in that timezone on **each query**, so date transitions need no restart.
- Data loads once at startup: restart after editing. Invalid types, dates, references, duplicate YAML keys, alias collisions, and boolean/negative/nonfinite rates are rejected. YAML merges that override keys are also rejected; use explicit unique fields.

Rankings do not account for exhausted caps, activation status, or merchant-specific eligibility. They show conditional published rates for you to assess, not guaranteed earnings. Review issuer terms. Keep real card details private; do not commit them to a public repository.

### Chase points versus cashback

For Chase Ultimate Rewards cards, use `rewards_program: chase_ultimate_rewards`, `base_points_per_dollar`, and `points_per_dollar` instead of cashback fields. Do not mix units on a card. Other points programs are not supported.

Example card entry (verify current terms before using):

```yaml
  - id: sapphire_preferred
    name: Chase Sapphire Preferred
    rewards_program: chase_ultimate_rewards
    base_points_per_dollar: 1
    rewards:
      - category: restaurant
        points_per_dollar: 3
        conditions:
          - Eligible dining purchases only.
```

Ranking formula: **points per dollar × cents per point = estimated reward %**. Newly earned Chase points are valued conservatively at **1¢ each**, assuming redemption through Sapphire Preferred's Chase Travel portal. Thus 3x points ranks equally with 3% cashback; the estimate is travel value, not cash paid back.

The same valuation applies to other Chase cards only if you combine their points into Sapphire Preferred. [Points Boost](https://www.chase.com/travel/guide/travel-benefits/points-boost-offers) is booking-specific and excluded; legacy redemption rates on older eligible points do not apply to new spending. No live portal scraping or account access is required. The default is defined by `CHASE_POINT_VALUE_CENTS` in `rewards.py`.

After editing the host `cards.yaml`, run `docker compose restart` to reload it. No rebuild is needed; the file is mounted read-only in the container.

## Local development

Use Python 3.12 or newer:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

To run without Docker, export `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID`, then run `.venv/bin/python bot.py`. Python does not automatically load `.env`. On Windows, use `.venv\Scripts\python` instead.
