"""Owner-only Telegram lookup bot; data is loaded once at startup."""

from datetime import datetime
import logging
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from rewards import CHASE_POINT_VALUE_CENTS, load_cards, normalize_category, recommend

logger = logging.getLogger(__name__)
LIMITATIONS = "Published rates only: rankings do not account for exhausted caps, activation status, or merchant-specific eligibility."
POINTS_NOTE = f"🧮 Chase points valued at {CHASE_POINT_VALUE_CENTS:g}¢ each via Sapphire Preferred’s Chase Travel portal."
CATEGORY_LABELS = {
    "grocery": "🛒 Groceries", "restaurant": "🍽 Dining",
    "entertainment": "🎟 Entertainment", "shopping": "🛍 Shopping",
    "travel": "✈️ Travel", "gas": "⛽ Gas",
}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, "🏷 " + category.replace("_", " ").title())


def rate_label(rate, points=False):
    if points:
        return f"{rate:g}x Chase points ≈ {rate * CHASE_POINT_VALUE_CENTS:g}%"
    return f"{rate:g}%"


def format_recommendations(category: str, results: list[dict]) -> str:
    if not results:
        return "💳 No cards configured yet."
    lines = [category_label(category), ""]
    for medal, result in zip(("🥇", "🥈", "🥉"), results):
        points = "points_per_dollar" in result
        rate = result["points_per_dollar"] if points else result["reward_percent"]
        lines.append(f"{medal} {result['name']} — {rate_label(rate, points)}")
    winners = [r["name"] for r in results if r["reward_percent"] == results[0]["reward_percent"]]
    heading = "Best choice" if len(winners) == 1 else "Best choices"
    lines.extend(["", f"{heading}: {', '.join(winners)}"])
    if any("points_per_dollar" in r and (i < 3 or r["reward_percent"] == results[0]["reward_percent"])
           for i, r in enumerate(results)):
        lines.extend(["", POINTS_NOTE])
    return "\n".join(lines)


def format_card(card: dict) -> str:
    points = "rewards_program" in card
    field = "points_per_dollar" if points else "cashback_percent"
    lines = [f"💳 {card['name']}", "", f"💰 Base — {rate_label(card['base_' + field], points)}"]
    for rule in card["rewards"]:
        period = (f"{rule['starts_on'].isoformat()} through {rule['ends_on'].isoformat()} (inclusive)"
                  if "starts_on" in rule else "Ongoing")
        lines.extend(["", f"{category_label(rule['category'])} — {rate_label(rule[field], points)}",
                      f"📅 {period}"])
        lines.extend(f"• {condition}" for condition in rule["conditions"])
    if card["rewards"]:
        lines.extend(["", "⚠️ Offers are separate, not stackable; check each offer's conditions and dates."])
    for benefit in card["benefits"]:
        categories = ", ".join(category_label(c) for c in benefit["categories"]) or "All categories"
        lines.extend(["", f"🎁 {benefit['name']}", f"{benefit['description']}", f"🏷 Applies to: {categories}"])
    if points:
        lines.extend(["", POINTS_NOTE,
                      "🚀 Points Boost is booking-specific and excluded from rankings. Legacy rates on older points do not apply to new spending.",
                      "🔗 https://www.chase.com/travel/guide/travel-benefits/points-boost-offers",
                      "🔄 Assumes Chase points are combined into Sapphire Preferred for redemption."])
    lines.extend(["", "⚠️ " + LIMITATIONS])
    return "\n".join(lines)


def split_reply(text: str, limit: int = 4096) -> list[str]:
    if limit < 2:
        raise ValueError("Reply limit must be at least 2 UTF-16 code units")
    chunks = []
    start = units = 0
    for index, character in enumerate(text):
        size = 2 if ord(character) > 0xFFFF else 1
        if units + size > limit:
            chunks.append(text[start:index])
            start, units = index, 0
        units += size
    if start < len(text):
        chunks.append(text[start:])
    return [chunk for chunk in chunks if chunk.strip()]


def is_authorized(update: Update, allowed_user_id: int) -> bool:
    return bool(isinstance(update, Update) and update.effective_user
                and update.effective_user.id == allowed_user_id
                and update.effective_chat and update.effective_chat.type == "private"
                and update.effective_message)


async def _reply(update, text):
    for chunk in split_reply(text):
        await update.effective_message.reply_text(chunk)


def _categories(data):
    return "📂 Categories\n" + "\n".join(f"{category_label(c)} ({c})" for c in data["categories"])


async def help_command(update, context):
    if not is_authorized(update, context.bot_data["allowed_user_id"]):
        return
    data = context.bot_data["data"]
    await _reply(update, "👋 Send a category to see your top three cards.\n"
                 "💬 Example: " + next(iter(data["categories"]))
                 + "\n\n📂 /categories — spending categories"
                 + "\n💳 /cards — your cards"
                 + "\n📖 /card <name or ID> — full card details"
                 + "\n\n" + _categories(data)
                 + "\n\n⚠️ Rankings use published rates; check /card for conditions.")


async def categories_command(update, context):
    if is_authorized(update, context.bot_data["allowed_user_id"]):
        await _reply(update, _categories(context.bot_data["data"]))


def _card_list(cards):
    if not cards:
        return "💳 No cards configured yet."
    return "💳 Your cards\n\n" + "\n".join(f"💳 {c['name']} — /card {c['id']}" for c in cards)


async def cards_command(update, context):
    if is_authorized(update, context.bot_data["allowed_user_id"]):
        await _reply(update, _card_list(context.bot_data["data"]["cards"]))


async def card_command(update, context):
    if not is_authorized(update, context.bot_data["allowed_user_id"]):
        return
    cards = context.bot_data["data"]["cards"]
    name = " ".join(context.args).strip().casefold()
    if not name:
        await _reply(update, "📖 Use /card <name or ID>.\n\n" + _card_list(cards))
        return
    matches = [c for c in cards if name == c["id"].casefold()]
    if not matches:
        matches = [c for c in cards if name == c["name"].casefold()]
    if not matches:
        matches = [c for c in cards if name in c["name"].casefold()]
    if len(matches) == 1:
        await _reply(update, format_card(matches[0]))
    elif matches:
        await _reply(update, "🔎 Multiple cards match. Use a full name or ID.\n\n" + _card_list(matches))
    else:
        await _reply(update, "🔎 Card not found. Use /cards to see your cards.")


async def query(update, context):
    if not is_authorized(update, context.bot_data["allowed_user_id"]):
        return
    data = context.bot_data["data"]
    category = normalize_category(data, update.effective_message.text or "")
    if category is None:
        await _reply(update, "🔎 Unknown category.\n\n" + _categories(data)
                     + "\n\n💬 Example: " + next(iter(data["categories"])))
        return
    today = datetime.now(ZoneInfo(data["timezone"])).date()
    await _reply(update, format_recommendations(category, recommend(data, category, today)))


async def error_handler(update, context):
    error = context.error
    logger.error("Unexpected Telegram handler failure", exc_info=(type(error), error, error.__traceback__))
    if is_authorized(update, context.bot_data["allowed_user_id"]):
        try:
            await _reply(update, "⚠️ Could not process that query; please try again later.")
        except Exception:
            logger.exception("Could not send failure reply")


class SafeFormatter(logging.Formatter):
    """Redact credentials even when external exceptions include request URLs."""

    def __init__(self, token):
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.token = token

    def format(self, record):
        text = super().format(record)
        if self.token:
            text = text.replace(self.token, "[REDACTED]")
        return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot[REDACTED]", text)


def read_config():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN: set the token provided by @BotFather")
    user_id = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not user_id.isascii() or not user_id.isdecimal() or int(user_id) <= 0:
        raise ValueError("TELEGRAM_ALLOWED_USER_ID: set your positive numeric Telegram user ID")
    return token, int(user_id)


def main() -> None:
    try:
        token, allowed_user_id = read_config()
        data = load_cards(str(Path(__file__).with_name("cards.yaml")))
    except ValueError as error:
        raise SystemExit(f"Startup configuration error: {error}") from None
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeFormatter(token))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        application = Application.builder().token(token).build()
        application.bot_data.update(data=data, allowed_user_id=allowed_user_id)
        application.add_handler(CommandHandler(["start", "help"], help_command))
        application.add_handler(CommandHandler("categories", categories_command))
        application.add_handler(CommandHandler("cards", cards_command))
        application.add_handler(CommandHandler("card", card_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, query))
        application.add_error_handler(error_handler)
        application.run_polling(allowed_updates=["message"])
    except Exception:
        logger.exception("Bot startup/runtime failed; check token, network, and running bot instances")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
