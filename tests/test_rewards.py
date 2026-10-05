import copy
from datetime import date
from pathlib import Path
import tempfile
import unittest

import yaml

from rewards import load_cards, normalize_category, recommend


def fixture():
    return {
        "timezone": "America/New_York",
        "categories": {"grocery": {"aliases": ["groceries"]}, "shopping": {"aliases": []}},
        "cards": [
            {"id": "a", "name": "Alpha", "base_cashback_percent": 1,
             "rewards": [{"category": "grocery", "cashback_percent": 5,
                          "starts_on": "2026-10-01", "ends_on": "2026-12-31",
                          "conditions": ["Activation required."]}],
             "benefits": [{"name": "Global", "categories": [], "description": "All purchases"},
                          {"name": "Shopping", "categories": ["shopping"], "description": "Protection"}]},
            {"id": "b", "name": "Beta", "base_cashback_percent": 1},
        ],
    }


class RewardTests(unittest.TestCase):
    def load(self, raw):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cards.yaml"
            path.write_text(yaml.safe_dump(raw), encoding="utf-8")
            return load_cards(str(path))

    def test_aliases_boundaries_and_empty_cards(self):
        data = self.load(fixture())
        self.assertEqual(normalize_category(data, " GROCERIES "), "grocery")
        self.assertIsNone(normalize_category(data, "unknown"))
        for day, rate in [(date(2026, 9, 30), 1), (date(2026, 10, 1), 5),
                          (date(2026, 12, 31), 5), (date(2027, 1, 1), 1)]:
            with self.subTest(day=day):
                self.assertEqual(recommend(data, "grocery", day)[0]["reward_percent"], rate)
        self.assertEqual(recommend({**data, "cards": []}, "grocery", date.today()), [])

    def test_ranking_base_fallback_and_all_winning_conditions(self):
        raw = fixture()
        raw["cards"][0]["rewards"].append({"category": "grocery", "cashback_percent": 5,
                                           "conditions": ["Excludes clubs."]})
        results = recommend(self.load(raw), "grocery", date(2026, 10, 1))
        self.assertEqual([r["id"] for r in results], ["a", "b"])
        self.assertEqual([r["conditions"] for r in results[0]["rules"]],
                         [["Activation required."], ["Excludes clubs."]])
        raw["cards"][1]["base_cashback_percent"] = 6
        raw["cards"][1]["rewards"] = [{"category": "grocery", "cashback_percent": 2,
                                       "conditions": ["Not relevant"]}]
        results = recommend(self.load(raw), "grocery", date(2026, 10, 1))
        self.assertEqual(results[0]["id"], "b")
        self.assertEqual(results[0]["rules"], [])
        raw["cards"][0]["name"] = "beta"
        raw["cards"][0]["base_cashback_percent"] = 6
        self.assertEqual([r["id"] for r in recommend(self.load(raw), "shopping", date.today())], ["a", "b"])

    def test_dates_defaults_normalized_keys_and_benefits(self):
        raw = fixture()
        raw["categories"] = {" Grocery ": {"aliases": [" GROCERIES "]}, "shopping": {"aliases": []}}
        raw["cards"][0]["rewards"][0]["starts_on"] = date(2026, 10, 1)
        data = self.load(raw)
        self.assertEqual(data["cards"][0]["rewards"][0]["starts_on"], date(2026, 10, 1))
        self.assertEqual(data["cards"][1]["rewards"], [])
        self.assertEqual(data["cards"][1]["benefits"], [])
        self.assertEqual([b["name"] for b in recommend(data, "grocery", date(2026, 10, 1))[0]["benefits"]], ["Global"])
        self.assertEqual([b["name"] for b in recommend(data, "shopping", date.today())[0]["benefits"]], ["Global", "Shopping"])

    def test_chase_points_rank_at_one_cent_and_expired_rules_fall_back(self):
        raw = fixture()
        raw["cards"][1] = {
            "id": "sapphire", "name": "Chase Sapphire Preferred",
            "rewards_program": "chase_ultimate_rewards", "base_points_per_dollar": 1,
            "rewards": [{"category": "grocery", "points_per_dollar": 3,
                         "starts_on": "2026-10-01", "ends_on": "2026-12-31",
                         "conditions": ["Eligible purchases only."]}],
        }
        data = self.load(raw)
        results = recommend(data, "grocery", date(2026, 10, 1))
        self.assertEqual([r["id"] for r in results], ["a", "sapphire"])
        self.assertEqual(results[1]["reward_percent"], 3)
        self.assertEqual(results[1]["points_per_dollar"], 3)
        raw["cards"][0]["rewards"][0]["cashback_percent"] = 2
        self.assertEqual(recommend(self.load(raw), "grocery", date(2026, 10, 1))[0]["id"], "sapphire")
        expired = recommend(data, "grocery", date(2027, 1, 1))[1]
        self.assertEqual(expired["reward_percent"], 1)
        self.assertEqual(expired["points_per_dollar"], 1)
        self.assertEqual(expired["rules"], [])

    def test_point_schema_rejects_unknown_programs_mixed_units_and_invalid_rates(self):
        card = {"id": "sapphire", "name": "Sapphire", "rewards_program": "chase_ultimate_rewards",
                "base_points_per_dollar": 1,
                "rewards": [{"category": "grocery", "points_per_dollar": 3}]}
        cases = []
        for value in [-1, True, float("nan"), float("inf"), "3"]:
            for field in ["base_points_per_dollar", "points_per_dollar"]:
                bad = copy.deepcopy(card)
                (bad if field.startswith("base") else bad["rewards"][0])[field] = value
                cases.append((bad, field))
        cases.extend([
            ({**card, "rewards_program": "unknown"}, "rewards_program"),
            ({**card, "base_cashback_percent": 1}, "base_cashback_percent"),
            ({**card, "rewards": [{"category": "grocery", "cashback_percent": 3}]}, "cashback_percent"),
            ({**card, "rewards": [{"category": "grocery", "points_per_dollar": 3, "cashback_percent": 3}]}, "cashback_percent"),
            ({"id": "a", "name": "Alpha", "base_points_per_dollar": 1}, "rewards_program"),
            ({"id": "a", "name": "Alpha", "base_cashback_percent": 1,
              "rewards": [{"category": "grocery", "points_per_dollar": 3}]}, "points_per_dollar"),
        ])
        for bad, field in cases:
            with self.subTest(card=bad), self.assertRaisesRegex(ValueError, field):
                self.load({**fixture(), "cards": [bad]})

    def test_invalid_data_has_useful_field_paths(self):
        cases = [([], "document"),
                 ({**fixture(), "timezone": "not/a-zone"}, "timezone"),
                 ({**fixture(), "categories": {"grocery": {"aliases": [" GROCERY "]}}}, "categories"),
                 ({**fixture(), "categories": {"grocery": {"aliases": ["x"]}, " X ": {"aliases": []}}}, "categories"),
                 ({**fixture(), "cards": "bad"}, "cards")]
        for field in ["timezone", "categories", "cards"]:
            raw = fixture()
            del raw[field]
            cases.append((raw, field))
        for value in [-1, True, float("nan"), float("inf"), "5"]:
            for field in ["base_cashback_percent", "cashback_percent"]:
                raw = fixture()
                target = raw["cards"][0] if field == "base_cashback_percent" else raw["cards"][0]["rewards"][0]
                target[field] = value
                cases.append((raw, field))
        for field, value in [("id", ""), ("name", 5), ("rewards", {}), ("benefits", "bad")]:
            raw = fixture()
            raw["cards"][0][field] = value
            cases.append((raw, field))
        raw = fixture()
        raw["cards"][1]["id"] = "a"
        cases.append((raw, "id"))
        for field, value in [("category", "unknown"), ("conditions", "bad"),
                             ("conditions", [False]), ("ends_on", "2026-09-01"),
                             ("starts_on", "bad-date"), ("starts_on", None)]:
            raw = fixture()
            raw["cards"][0]["rewards"][0][field] = value
            cases.append((raw, field))
        raw = fixture()
        del raw["cards"][0]["rewards"][0]["ends_on"]
        cases.append((raw, "ends_on"))
        for field, value in [("categories", ["unknown"]), ("categories", "shopping"),
                             ("name", " "), ("description", 1)]:
            raw = fixture()
            raw["cards"][0]["benefits"][0][field] = value
            cases.append((raw, field))
        for raw, field in cases:
            with self.subTest(field=field, raw=raw):
                with self.assertRaisesRegex(ValueError, field):
                    self.load(copy.deepcopy(raw))

    def test_duplicate_yaml_keys_cannot_hide_categories_or_conditions(self):
        documents = [
            "timezone: America/New_York\ncategories:\n  grocery: {aliases: [groceries]}\n  grocery: {aliases: []}\ncards: []\n",
            "timezone: America/New_York\ncategories: {grocery: {aliases: []}}\ncards:\n"
            "  - id: a\n    name: Alpha\n    base_cashback_percent: 1\n    rewards:\n"
            "      - category: grocery\n        cashback_percent: 5\n"
            "        conditions: [Activation required.]\n        conditions: []\n",
        ]
        for document in documents:
            with self.subTest(document=document), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "cards.yaml"
                path.write_text(document, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    load_cards(str(path))

    def test_ids_are_unique_after_casefolding(self):
        raw = fixture()
        raw["cards"][0]["id"] = "Flex"
        raw["cards"][1]["id"] = "flex"
        with self.assertRaisesRegex(ValueError, "id: duplicate"):
            self.load(raw)

    def test_malformed_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cards.yaml"
            path.write_text("cards: [", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "YAML"):
                load_cards(str(path))


if __name__ == "__main__":
    unittest.main()
