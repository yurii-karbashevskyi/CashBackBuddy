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
    def test_categories_use_specific_emojis_or_plain_text_not_generic_tags(self):
        data = {"categories": {c: {} for c in ["ev_charging", "drugstore", "streaming", "walmart", "target", "custom_category"]}}
        text = bot._categories(data)
        for label in ["⚡ EV Charging", "💊 Drugstores", "📺 Streaming", "Walmart", "Target", "Custom Category"]:
            self.assertIn(label, text)
        self.assertNotIn("🏷", text)

    def test_main_list_hides_special_offers_but_retains_qualified_queries(self):
        keys = ["travel", "entertainment", "walmart", "target", "chase_travel",
                "capital_one_travel", "capital_one_entertainment", "red_cross", "t_mobile_dining"]
        data = {"categories": {c: {"aliases": []} for c in keys}}
        text = bot._categories(data)
        for key in keys[:4]:
            self.assertIn(f"({key})", text)
        for key in keys[4:]:
            self.assertNotIn(f"({key})", text)
        self.assertEqual(bot.normalize_category(data, "chase_travel"), "chase_travel")
        self.assertIn("portal", bot.category_label("chase_travel").lower())
        self.assertIn("portal", bot.category_label("capital_one_entertainment").lower())

    def test_empty_and_complete_recommendation(self):
        self.assertEqual(bot.format_recommendations("grocery", []), "💳 No cards configured yet.")
        result = [{"id": "a", "name": "Alpha", "reward_percent": 5,
                   "rules": [{"starts_on": date(2026, 10, 1), "ends_on": date(2026, 12, 31),
                              "conditions": ["Activation required", "$1,500 cap"]},
                             {"conditions": ["Excludes clubs"]}],
                   "benefits": [{"name": "Protection", "description": "Terms apply"}]}]
        text = bot.format_recommendations("grocery", result)
        self.assertEqual(text, "🛒 Groceries\n\n🥇 Alpha — 5%\n\nBest choice: Alpha")

    def test_top_three_points_and_ties_do_not_hide_other_winners(self):
        results = [{"id": str(i), "name": name, "reward_percent": 3,
                    "rules": [], "benefits": []}
                   for i, name in enumerate(["Alpha", "Beta", "Gamma", "Delta"])]
        results[0]["points_per_dollar"] = 3
        text = bot.format_recommendations("restaurant", results)
        self.assertIn("🍽 Dining", text)
        self.assertIn("🥇 Alpha — 3x Chase points ≈ 3%", text)
        self.assertIn("🥈 Beta — 3%", text)
        self.assertIn("🥉 Gamma — 3%", text)
        self.assertNotIn("Delta —", text)
        self.assertIn("Best choices: Alpha, Beta, Gamma, Delta", text)
        self.assertIn("1¢", text)

    def test_full_card_details_include_all_rules_benefits_and_valuation(self):
        card = {"id": "sapphire", "name": "Chase Sapphire Preferred",
                "rewards_program": "chase_ultimate_rewards", "base_points_per_dollar": 1,
                "rewards": [{"category": "restaurant", "points_per_dollar": 3,
                             "conditions": ["Eligible dining only"]},
                            {"category": "grocery", "points_per_dollar": 5,
                             "starts_on": date(2026, 10, 1), "ends_on": date(2026, 12, 31),
                             "conditions": ["Activation required", "$1,500 cap"]}],
                "benefits": [{"name": "Protection", "description": "Terms apply", "categories": ["shopping"]}]}
        text = bot.format_card(card)
        for required in ["💳 Chase Sapphire Preferred", "1x", "🍽 Dining", "3x", "🛒 Groceries", "5x",
                         "2026-10-01", "2026-12-31", "Eligible dining only", "Activation required",
                         "$1,500 cap", "Protection", "Terms apply", "Shopping", "1¢", "Points Boost",
                         "caps", "activation", "merchant", "not stackable"]:
            self.assertIn(required, text)

    def test_chase_winner_outside_top_three_keeps_portal_valuation_note(self):
        results = [{"id": str(i), "name": name, "reward_percent": 3,
                    "rules": [], "benefits": []}
                   for i, name in enumerate(["Alpha", "Beta", "Gamma", "Sapphire"])]
        results[3]["points_per_dollar"] = 3
        text = bot.format_recommendations("restaurant", results)
        self.assertIn("Best choices: Alpha, Beta, Gamma, Sapphire", text)
        self.assertIn("1¢", text)
        self.assertIn("Sapphire Preferred", text)
        self.assertIn("Chase Travel", text)

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
        self.context = SimpleNamespace(bot_data={"data": self.data, "allowed_user_id": 123}, error=RuntimeError("failure"), args=[])

    async def test_no_responses_to_other_users_or_groups(self):
        for denied in [update(456), update(123, "group"), Update(1)]:
            self.assertFalse(bot.is_authorized(denied, 123))
            with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
                for handler in [bot.query, bot.help_command, bot.categories_command, bot.cards_command, bot.card_command, bot.error_handler]:
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
            reply.assert_awaited_once_with("💳 No cards configured yet.")

    async def test_unknown_category_and_help_show_choices(self):
        for handler, text in [(bot.query, "unknown"), (bot.help_command, "/help"), (bot.categories_command, "/categories")]:
            with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
                await handler(update(text=text), self.context)
                self.assertIn("grocery", reply.call_args.args[0])
                self.assertNotIn("failed", reply.call_args.args[0])
                self.assertTrue(any(ord(c) > 0x2000 for c in reply.call_args.args[0]))

    async def test_card_commands_list_lookup_and_report_missing_or_ambiguous_names(self):
        self.data["cards"] = [
            {"id": "sapphire", "name": "Chase Sapphire Preferred", "base_cashback_percent": 1,
             "rewards": [], "benefits": []},
            {"id": "flex", "name": "Chase Freedom Flex", "base_cashback_percent": 1,
             "rewards": [], "benefits": []},
        ]
        with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
            await bot.cards_command(update(text="/cards"), self.context)
            text = reply.call_args.args[0]
            self.assertIn("💳", text)
            self.assertIn("/card sapphire", text)
            self.assertIn("Chase Freedom Flex", text)
            for args in [["sapphire"], ["CHASE", "SAPPHIRE", "PREFERRED"], ["Sapphire"]]:
                self.context.args = args
                await bot.card_command(update(text="/card"), self.context)
                self.assertIn("💳 Chase Sapphire Preferred", reply.call_args.args[0])
                self.assertIn("Base", reply.call_args.args[0])
                self.assertNotIn("Chase Freedom Flex", reply.call_args.args[0])
            for args, expected in [([], "/card"), (["missing"], "not found"), (["Chase"], "Multiple")]:
                self.context.args = args
                await bot.card_command(update(text="/card"), self.context)
                self.assertIn(expected, reply.call_args.args[0])

    async def test_empty_card_list_and_help_commands(self):
        with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
            await bot.cards_command(update(text="/cards"), self.context)
            self.assertIn("💳 No cards", reply.call_args.args[0])
            await bot.help_command(update(text="/help"), self.context)
            for command in ["/cards", "/card", "/categories"]:
                self.assertIn(command, reply.call_args.args[0])

    async def test_help_leaves_category_list_to_categories_command(self):
        self.data["categories"]["restaurant"] = {"aliases": ["dining"]}
        with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
            await bot.help_command(update(text="/start"), self.context)
            text = reply.call_args.args[0]
            self.assertIn("/categories", text)
            self.assertIn("Example: grocery", text)
            self.assertNotIn("🍽 Dining", text)
            self.assertNotIn("📂 Categories", text)
            await bot.categories_command(update(text="/categories"), self.context)
            self.assertIn("🍽 Dining", reply.call_args.args[0])

    async def test_exact_id_takes_priority_over_another_cards_name(self):
        self.data["cards"] = [
            {"id": "flex", "name": "Chase Freedom Flex", "base_cashback_percent": 1,
             "rewards": [], "benefits": []},
            {"id": "other", "name": "Flex", "base_cashback_percent": 2,
             "rewards": [], "benefits": []},
        ]
        self.context.args = ["FLEX"]
        with patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
            await bot.card_command(update(text="/card FLEX"), self.context)
            self.assertIn("💳 Chase Freedom Flex", reply.call_args.args[0])
            self.assertNotIn("Multiple", reply.call_args.args[0])

    async def test_error_reply_is_authorized_and_brief(self):
        with self.assertLogs("bot", level="ERROR"), patch.object(Message, "reply_text", new_callable=AsyncMock) as reply:
            await bot.error_handler(update(), self.context)
            reply.assert_awaited_once()
            self.assertIn("try again", reply.call_args.args[0])
            self.assertNotIn("RuntimeError", reply.call_args.args[0])


from contextlib import nullcontext as _no_logs

if __name__ == "__main__":
    unittest.main()
