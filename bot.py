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

from rewards import load_cards, normalize_category, recommend

logger = logging.getLogger(__name__)
LIMITATIONS = "Published rates only: rankings do not account for exhausted caps, activation status, or merchant-specific eligibility."


def format_recommendations(category: str, results: list[dict]) -> str:
    if not results:
        return "No cards configured yet."
    lines = [f"Cards for {category}:"]
    for result in results:
        lines.extend(["", f"{result['name']}: {result['cashback_percent']:g}% cashback"])
        if not result["rules"]:
            lines.append("Base rate.")
        if len(result["rules"]) > 1:
            lines.append("Equal-rate offers are separate, not stackable; check each offer's conditions.")
        for rule in result["rules"]:
            period = f"{rule['starts_on'].isoformat()} through {rule['ends_on'].isoformat()} (inclusive)" if "starts_on" in rule else "Ongoing"
            lines.append(f"Offer: {period}")
            lines.extend(f"- {condition}" for condition in rule["conditions"])
        for benefit in result["benefits"]:
            lines.append(f"Benefit: {benefit['name']} — {benefit['description']}")
    lines.extend(["", LIMITATIONS])
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
    return "Supported categories: " + ", ".join(data["categories"])


async def help_command(update, context):
    if not is_authorized(update, context.bot_data["allowed_user_id"]):
        return
    data = context.bot_data["data"]
    await _reply(update, "Send a category or alias to rank your cards. Example: "
                 + next(iter(data["categories"])) + "\n" + _categories(data)
                 + "\nUse /categories for choices.\n" + LIMITATIONS)


async def categories_command(update, context):
    if is_authorized(update, context.bot_data["allowed_user_id"]):
        await _reply(update, _categories(context.bot_data["data"]))


async def query(update, context):
    if not is_authorized(update, context.bot_data["allowed_user_id"]):
        return
    data = context.bot_data["data"]
    category = normalize_category(data, update.effective_message.text or "")
    if category is None:
        await _reply(update, "Unknown category. " + _categories(data)
                     + ". Example: " + next(iter(data["categories"])))
        return
    today = datetime.now(ZoneInfo(data["timezone"])).date()
    await _reply(update, format_recommendations(category, recommend(data, category, today)))


async def error_handler(update, context):
    error = context.error
    logger.error("Unexpected Telegram handler failure", exc_info=(type(error), error, error.__traceback__))
    if is_authorized(update, context.bot_data["allowed_user_id"]):
        try:
            await _reply(update, "Could not process that query; please try again later.")
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
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, query))
        application.add_error_handler(error_handler)
        application.run_polling(allowed_updates=["message"])
    except Exception:
        logger.exception("Bot startup/runtime failed; check token, network, and running bot instances")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
