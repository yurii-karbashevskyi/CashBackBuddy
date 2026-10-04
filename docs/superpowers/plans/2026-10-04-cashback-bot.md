# CashBackBuddy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. The user requested this repository and plan for execution in a new session; confirm the execution method before implementation.

**Goal:** Build a personal, read-only Telegram bot recommending credit cards by spending category.

**Architecture:** Load validated YAML once at startup. Independent reward logic evaluates active rules for the date of each query. Run Telegram long polling continuously in Docker Compose.

**Tech Stack:** Python 3.12, python-telegram-bot, PyYAML, standard-library unittest; tzdata on Windows if system timezone data is unavailable.

**Spec:** `docs/superpowers/specs/2026-10-04-cashback-bot-design.md`

## Global Constraints

- Project root is this CashBackBuddy repository; do not create another nested project.
- Telegram is read-only; actual card data comes later. Start with categories and `cards: []`.
- No bank integration, transaction tracking, database, LLM, or fuzzy matching.
- Rates are total cashback percentages; show conditions without tracking caps or activation.
- Personal private-chat access only, configured through environment variables.
- Load YAML at startup; use the configured timezone per query; restart to reload edits.
- One Docker container, read-only YAML mount, `restart: unless-stopped`, no inbound ports.
- Do not commit or push unless the user explicitly requests it. Git initialization is already complete.

## Review Focus

1. YAML booleans, NaN, and infinity are not valid cashback numbers: test rejection in Task 1.
2. Capitalization or whitespace must not hide alias collisions: test normalized collisions in Task 1.
3. Equal-rate rules must not silently lose restrictions: test combined winning conditions in Task 1.
4. Group messages and other users must never receive personal card data: test both in Task 2.
5. Many cards or long conditions must not exceed Telegram's reply limit: test splitting in Task 2.

## File ownership

- `rewards.py`: YAML loading/validation, category normalization, rule selection, ranking.
- `bot.py`: environment configuration, access checks, formatting, handlers, startup.
- `cards.yaml`: initial supported categories and empty card list.
- `tests/test_rewards.py`, `tests/test_bot.py`: focused unittest checks.
- `requirements.txt`, `.env.example`, `.gitignore`: dependencies and local configuration.
- `Dockerfile`, `.dockerignore`, `compose.yaml`: container build and runtime.
- `README.md`: installation, data editing, usage, deployment, verification.

## Task 1: Validated card data and reward selection

**Files:** Create rewards.py, cards.yaml, requirements.txt, .gitignore, tests/test_rewards.py.

**Interfaces produced:**

```python
load_cards(path: str) -> dict
normalize_category(data: dict, text: str) -> str | None
recommend(data: dict, category: str, today: date) -> list[dict]
```

`load_cards` uses yaml.safe_load and raises ValueError with a useful field path for invalid data. Return normalized data with date objects for dated rules. Optional rewards, benefits, and conditions default to empty lists. Require timezone, categories, cards, and each card's id/name/base_cashback_percent. Normalize category keys and aliases with strip/casefold; reject empty or colliding names.

Recommendation dictionaries contain `id`, `name`, `cashback_percent`, `rules` (the winning active category-rule dictionaries), and `benefits`. Base-only results have `rules: []`. If base exceeds category rewards, return base without unrelated rule conditions. Preserve all equally highest matching rules and their conditions. Sort by descending cashback_percent and casefolded name, with id as a stable final tie-break.

- [ ] Write failing unittest cases with an inline two-card fixture and a temporary YAML file. Example assertions:

```python
self.assertEqual(normalize_category(data, " GROCERIES "), "grocery")
self.assertIsNone(normalize_category(data, "unknown"))
self.assertEqual(recommend(data, "grocery", date(2026, 10, 1))[0]["cashback_percent"], 5)
self.assertEqual(recommend(data, "grocery", date(2026, 12, 31))[0]["cashback_percent"], 5)
self.assertEqual(recommend(data, "grocery", date(2027, 1, 1))[0]["cashback_percent"], 1)
self.assertEqual(recommend({**data, "cards": []}, "grocery", date(2026, 10, 1)), [])
```

Use unittest subtests for invalid cases: duplicate IDs, unknown categories, normalized alias collisions, bad list/text types, missing dates, reversed dates, invalid timezone, negative rate, boolean rate, NaN/infinity, and malformed YAML. Add assertions for descending ranking, alphabetic ties, a lower category rate losing to base, multiple winning rules retaining conditions, ISO strings/unquoted YAML dates, and category-specific/global benefits.

- [ ] Run `python -m unittest discover -s tests -p test_rewards.py -v`; confirm failure from missing implementation.
- [ ] Implement the three interfaces in rewards.py, using standard-library datetime/zoneinfo, no generic repositories or service classes.
- [ ] Create cards.yaml with America/New_York, grocery aliases [groceries, supermarket, supermarkets], restaurant aliases [restaurants, dining], entertainment, shopping, and no cards. Add compatible dependency versions to requirements.txt; add a Windows-only tzdata dependency if needed. Ignore .env, virtual environments, bytecode, and caches.
- [ ] Install dependencies in a local virtual environment. Run the reward tests and confirm all pass; loading the checked-in YAML must also succeed.

## Task 2: Private Telegram queries

**Files:** Create bot.py, .env.example, tests/test_bot.py.

**Consumes:** All Task 1 interfaces and recommendation dictionary fields.

**Interfaces produced:**

```python
format_recommendations(category: str, results: list[dict]) -> str
split_reply(text: str, limit: int = 4096) -> list[str]
is_authorized(update: Update, allowed_user_id: int) -> bool
main() -> None
```

- [ ] Write failing tests using unittest.mock and IsolatedAsyncioTestCase. Assert empty results give `No cards configured yet.`; normal replies include each card's rate, dated period, conditions, and matching benefits. Assert limitations mention caps, activation, and merchant eligibility. Assert all split chunks are nonempty and at most 4096 characters, including a single overlong condition and non-BMP characters (conservatively count UTF-16 code units). Assert another user and an allowed user in a group get no reply. Assert an authorized private-chat alias query invokes recommendation logic with the date in the configured timezone. Assert unknown categories produce supported names, not a query error.
- [ ] Run `python -m unittest discover -s tests -p test_bot.py -v`; confirm expected missing-implementation failures.
- [ ] Implement the interfaces and async handlers in bot.py. Use plain text (no Markdown parse mode). Register /start, /help, /categories and text queries excluding commands. Check access before all responses. Compute datetime.now(ZoneInfo(data['timezone'])).date() per query. Load cards.yaml at startup; require a token and positive numeric user ID, with actionable errors. Use the script's directory to locate YAML.
- [ ] Add safe error handling: unexpected query failures log a traceback and send a brief failure reply only to an authorized private chat. Avoid logging environment values or request URLs containing the token; suppress noisy HTTP client logs. Test failed configuration and error-handler access restriction without real credentials.
- [ ] Create .env.example with placeholders only. Run `python -m unittest discover -s tests -v`; confirm all tests pass.

## Task 3: Homelab packaging and handoff

**Files:** Create Dockerfile, .dockerignore, compose.yaml; update README.md.

**Consumes:** `python bot.py` as the foreground process, requirements.txt, cards.yaml, and environment variables from Task 2.

- [ ] Create a Python 3.12 slim image that installs requirements, copies application code, and runs `python -u bot.py`. Exclude .git, .env, virtual environments, and caches from the build context; do not bake credentials into the image.
- [ ] Create compose.yaml with a single service, build context `.`, required TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID environment values, `restart: unless-stopped`, and `./cards.yaml:/app/cards.yaml:ro`. No ports or database volume. Use exec-form startup for graceful shutdown.
- [ ] Update README.md with local environment-variable setup, dependency installation, unit-test command, owner ID setup, YAML schema/example, startup/shutdown/log commands, and `docker compose restart` after data edits. Explain published-rate limitations, timezone selection, and empty-data behavior. Keep real card data and tokens out of documentation.
- [ ] Run `python -m unittest discover -s tests -v`. Run `docker compose config --quiet` with placeholder environment values, then `docker compose build`. Report Docker absence or daemon failure explicitly if blocked. Avoid printing rendered environment secrets.
- [ ] With user-provided credentials, run `docker compose up -d` and confirm /help, a category query, private-user restriction, expired-rule fallback, and reload after a host YAML edit/restart. Until real data is available, use clearly temporary smoke-test data and restore the empty file afterward. Do not claim live checks passed without credentials and actual Telegram responses.

## Completion and next-session handoff

Read the spec and this plan before writing code. Ask the user to select native or subagent-driven execution; then invoke the matching execution skill. Keep task progress visible and stop on genuine blockers. Verification must separate automated results from unavailable Docker/live Telegram checks. No commit or remote creation is currently authorized.
