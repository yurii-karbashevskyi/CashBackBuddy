from datetime import date, datetime
import logging
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from telegram import Chat, Message, Update, User

import bot


def update(user_id=123, chat_type="private", text=" GROCERIES "):
    user = User(user_id, "Owner", False)
    chat = Chat(123 if chat_type == "private" else -123, chat_type)
    message = Message(1, datetime.now(), chat, from_user=user, text=text)
    return Update(1, message=message)


class FormatTests(unittest.TestCase):
    def test_empty_and_complete_recommendation(self):
        self.assertEqual(bot.format_recommendations("grocery", []), "No cards configured yet.")
        result = [{"id": "a", "name": "Alpha", "cashback_percent": 5,
                   "rules": [{"starts_on": date(2026, 10, 1), "ends_on": date(2026, 12, 31),
                              "conditions": ["Activation required", "$1,500 cap"]},
                             {"conditions": ["Excludes clubs"]}],
                   "benefits": [{"name": "Protection", "description": "Terms apply"}]}]
        text = bot.format_recommendations("grocery", result)
        for required in ["Alpha", "5%", "2026-10-01", "2026-12-31", "Activation required",
                         "$1,500 cap", "Excludes clubs", "Protection", "Terms apply", "caps", "activation", "merchant", "not stackable"]:
            self.assertIn(required, text)

    def test_splitting_preserves_text_and_utf16_limits(self):
        for text in ["", "short", "Condition " + "x" * 12000, "😀" * 5000,
                     "Card\n" * 3000]:
            with self.subTest(length=len(text)):
                chunks = bot.split_reply(text)
                self.assertEqual("".join(chunks), text)
                self.assertTrue(all(0 < len(c.encode("utf-16-le")) // 2 <= 4096 for c in chunks))
        with self.assertRaises(ValueError):
            bot.split_reply("😀", 1)

    def test_splitting_never_emits_whitespace_only_messages(self):
        chunks = bot.split_reply("First" + " " * 12000 + "Last")
        self.assertTrue(all(chunk.strip() for chunk in chunks))
        self.assertEqual("".join(chunks).split(), ["First", "Last"])
        self.assertEqual(bot.split_reply(" \n\t"), [])

    def test_environment_validation_without_credentials(self):
        for env, field in [({}, "TELEGRAM_BOT_TOKEN"),
                           ({"TELEGRAM_BOT_TOKEN": "placeholder"}, "TELEGRAM_ALLOWED_USER_ID"),
                           ({"TELEGRAM_BOT_TOKEN": "placeholder", "TELEGRAM_ALLOWED_USER_ID": "0"}, "TELEGRAM_ALLOWED_USER_ID"),
                           ({"TELEGRAM_BOT_TOKEN": "placeholder", "TELEGRAM_ALLOWED_USER_ID": "abc"}, "TELEGRAM_ALLOWED_USER_ID")]:
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(ValueError, field):
                    bot.read_config()
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "placeholder", "TELEGRAM_ALLOWED_USER_ID": "123"}, clear=True):
            self.assertEqual(bot.read_config(), ("placeholder", 123))

    def test_log_formatter_redacts_token_in_exception(self):
        token = "123456:fake_secret"
        formatter = bot.SafeFormatter(token)
        try:
            raise RuntimeError(f"request https://api.telegram.org/bot{token}/sendMessage")
        except RuntimeError:
            import sys
            record = logging.LogRecord("test", logging.ERROR, __file__, 1, "Query failed", (), sys.exc_info())
        output = formatter.format(record)
        self.assertNotIn(token, output)
        self.assertIn("Traceback", output)


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.data = {"timezone": "America/New_York", "categories": {"grocery": {"aliases": ["groceries"]}}, "cards": []}
        self.context = SimpleNamespace(bot_data={"data": self.data, "allowed_user_id": 123}, error=RuntimeError("failure"))

    async def test_no_responses_to_other_users_or_groups(self):
        for denied in [update(456), update(123, "group"), Update(1)]:
            self.assertFalse(bot.is_authorized(denied, 123))
            with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
                for handler in [bot.query, bot.help_command, bot.categories_command, bot.error_handler]:
                    with self.assertLogs("bot", level="ERROR") if handler == bot.error_handler else _no_logs():
                        await handler(denied, self.context)
                reply.assert_not_awaited()

    async def test_authorized_alias_uses_configured_timezone_each_query(self):
        now = datetime(2027, 1, 1, 1, tzinfo=ZoneInfo("UTC"))
        with patch.object(bot, "datetime") as clock, patch.object(bot, "recommend", wraps=bot.recommend) as recommend, patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
            clock.now.side_effect = lambda zone: now.astimezone(zone)
            await bot.query(update(), self.context)
            recommend.assert_called_once_with(self.data, "grocery", date(2026, 12, 31))
            self.assertEqual(str(clock.now.call_args.args[0]), "America/New_York")
            reply.assert_awaited_once_with("No cards configured yet.")

    async def test_unknown_category_and_help_show_choices(self):
        for handler, text in [(bot.query, "unknown"), (bot.help_command, "/help"), (bot.categories_command, "/categories")]:
            with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
                await handler(update(text=text), self.context)
                self.assertIn("grocery", reply.call_args.args[0])
                self.assertNotIn("failed", reply.call_args.args[0])

    async def test_error_reply_is_authorized_and_brief(self):
        with self.assertLogs("bot", level="ERROR"), patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
            await bot.error_handler(update(), self.context)
            reply.assert_awaited_once()
            self.assertIn("try again", reply.call_args.args[0])
            self.assertNotIn("RuntimeError", reply.call_args.args[0])


from contextlib import nullcontext as _no_logs

if __name__ == "__main__":
    unittest.main()
