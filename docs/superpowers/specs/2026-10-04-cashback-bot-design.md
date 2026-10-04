# CashBackBuddy approved design

Approved by the user on 2026-10-04. Project name: CashBackBuddy.

## Purpose and scope

A personal, read-only Telegram bot helps its owner choose among their US-issued credit cards before a purchase. Send a category such as restaurant or grocery; receive cards ranked by published cashback rates, with restrictions and relevant benefits.

Version one includes static YAML data, ongoing and dated cashback rules, category queries, category help, personal access restriction, and Docker Compose deployment in a homelab.

Transaction tracking, bank connections, automatic offer discovery, and Telegram-based editing are deferred. Actual card data will be entered later. Issuer country is not stored.

## Structure and dependencies

```text
CashBackBuddy/
├── bot.py
├── rewards.py
├── cards.yaml
├── requirements.txt
├── Dockerfile
├── compose.yaml
├── .env.example
├── .gitignore
├── README.md
├── docs/superpowers/
└── tests/
    ├── test_rewards.py
    └── test_bot.py
```

`bot.py` loads data, checks access, handles messages, and formats replies. `rewards.py` normalizes categories, selects active rules, and ranks cards without depending on Telegram. `cards.yaml` stores categories, aliases, cards, rewards, and benefits.

Use python-telegram-bot and PyYAML. Use standard-library unittest for tests; no database, language model, or fuzzy matching.

## YAML contract

Illustration only; production data starts with an empty card list:

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

Rates are total percentages, not increments added to base rewards. Each card uses its highest active rate for the requested category, including its base rate. If equal-rate rules apply, display the conditions of all winning rules so restrictions are not hidden; do not describe distinct offers as stackable.

Dated rules require both dates, with inclusive boundaries. Expired and future rules are excluded; valid ongoing rules or base rates remain available. Activation and spending caps are displayed, not tracked.

Benefits are independent of ranking. Their category list selects where they appear; an empty list means all categories. Points and miles cannot be compared without an agreed valuation and are outside version-one ranking.

## Telegram behavior

- `/start` and `/help`: usage, supported categories, and limitations.
- `/categories`: supported category names.
- Category or alias: one entry per card, sorted by descending rate then card name.
- Unknown category: supported choices and an example query.
- Empty card list: `No cards configured yet.`

Matching ignores capitalization and surrounding whitespace. All configured cards appear, including base-rate-only cards. Replies show the rate, applicable dated period, conditions, and relevant benefits.

State that rankings do not account for exhausted caps, activation status, or merchant-specific eligibility. Conditional rates remain visible for the owner to assess. Use plain-text replies and split long replies to respect Telegram's message length limit.

Only the configured user's private-chat messages are processed. Unauthorized messages receive no card data.

## Runtime and deployment

One long-running Docker container uses Telegram long polling with `restart: unless-stopped`. No inbound ports or database are required; outbound access to Telegram is required.

Inject `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID` through environment variables, optionally using a local .env excluded from Git. Mount host cards.yaml read-only. Logs go to stdout without exposing the token.

Load and validate YAML once at startup. Edit the host file and restart the container to reload, without rebuilding the image. Evaluate rules on each query using the configured timezone, so quarter transitions do not require a restart.

## Validation and errors

Reject malformed YAML, invalid document structure, duplicate card IDs, non-finite or negative rates, unknown category references, conflicting normalized aliases, invalid timezones, incomplete dates, and reversed date ranges. Reject booleans as numeric rates. Require nonempty card IDs and names and correctly typed text fields and lists. Accept ISO date strings and YAML date values consistently.

An empty card list is valid. Missing environment configuration or invalid card data causes startup failure with an actionable error. Log unexpected query errors and send a short failure response rather than a recommendation; never log secrets.

## Acceptance checks

1. Category names and aliases return the same results.
2. Dated rewards apply on both boundary dates and expire afterward.
3. Highest active rate, base fallback, and deterministic ranking work.
4. Conditions and relevant benefits appear; invalid data is rejected.
5. Docker smoke testing confirms authorized replies, access restriction, and data updates after editing YAML and restarting.

Live Telegram verification requires the owner's token and user ID. Report this verification as blocked if credentials are unavailable, rather than claiming it passed.
