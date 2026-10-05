"""Validated static card data and cashback-equivalent recommendations."""

from datetime import date
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


# Newly earned points, redeemed through Sapphire Preferred; no booking-specific boosts.
CHASE_POINT_VALUE_CENTS = 1


class _UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"duplicate key {key!r}", key_node.start_mark)
            seen.add(key)
        return mapping


def _mapping(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a mapping")
    return value


def _list(value, path):
    if not isinstance(value, list):
        raise ValueError(f"{path}: expected a list")
    return value


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: expected nonempty text")
    return value.strip()


def _rate(value, path):
    if type(value) not in (int, float) or value < 0:
        raise ValueError(f"{path}: expected a finite nonnegative number, not a boolean")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path}: expected a finite nonnegative number")
    return value


def _date(value, path):
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ValueError(f"{path}: expected an ISO date (YYYY-MM-DD)")


def load_cards(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as source:
            data = yaml.load(source, Loader=_UniqueKeyLoader)
    except (yaml.YAMLError, OSError, UnicodeError) as error:
        raise ValueError(f"YAML {path}: unable to read valid data: {error}") from error
    _mapping(data, "document")
    timezone = _text(data.get("timezone"), "timezone")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("timezone: use a valid IANA name; install tzdata if unavailable") from error
    categories = {}
    names = set()
    for key, config in _mapping(data.get("categories"), "categories").items():
        category = _text(key, "categories.key").casefold()
        prefix = f"categories.{category}"
        _mapping(config, prefix)
        aliases = [_text(alias, f"{prefix}.aliases").casefold()
                   for alias in _list(config.get("aliases", []), f"{prefix}.aliases")]
        for name in [category, *aliases]:
            if name in names:
                raise ValueError(f"{prefix}: conflicting normalized category or alias {name!r}")
            names.add(name)
        categories[category] = {"aliases": aliases}
    if not categories:
        raise ValueError("categories: configure at least one category")

    def category_ref(value, field):
        category = _text(value, field).casefold()
        if category not in categories:
            raise ValueError(f"{field}: unknown category {category!r}")
        return category

    cards = []
    ids = set()
    for index, raw in enumerate(_list(data.get("cards"), "cards")):
        prefix = f"cards[{index}]"
        _mapping(raw, prefix)
        card_id = _text(raw.get("id"), f"{prefix}.id")
        if card_id.casefold() in ids:
            raise ValueError(f"{prefix}.id: duplicate ID {card_id!r}")
        ids.add(card_id.casefold())
        points = "rewards_program" in raw
        if points and raw["rewards_program"] != "chase_ultimate_rewards":
            raise ValueError(f"{prefix}.rewards_program: only chase_ultimate_rewards is supported")
        if not points and "base_points_per_dollar" in raw:
            raise ValueError(f"{prefix}.rewards_program: required for points cards")
        rate_field = "points_per_dollar" if points else "cashback_percent"
        other_field = "cashback_percent" if points else "points_per_dollar"
        base_field = "base_" + rate_field
        if "base_" + other_field in raw:
            raise ValueError(f"{prefix}.base_{other_field}: cannot mix points and cashback")
        card = {"id": card_id, "name": _text(raw.get("name"), f"{prefix}.name"),
                base_field: _rate(raw.get(base_field), f"{prefix}.{base_field}"),
                "rewards": [], "benefits": []}
        if points:
            card["rewards_program"] = raw["rewards_program"]
        for n, raw_rule in enumerate(_list(raw.get("rewards", []), f"{prefix}.rewards")):
            field = f"{prefix}.rewards[{n}]"
            _mapping(raw_rule, field)
            if other_field in raw_rule:
                raise ValueError(f"{field}.{other_field}: cannot mix points and cashback")
            rule = {"category": category_ref(raw_rule.get("category"), f"{field}.category"),
                    rate_field: _rate(raw_rule.get(rate_field), f"{field}.{rate_field}"),
                    "conditions": [_text(c, f"{field}.conditions") for c in
                                   _list(raw_rule.get("conditions", []), f"{field}.conditions")]}
            if "starts_on" in raw_rule or "ends_on" in raw_rule:
                for key in ("starts_on", "ends_on"):
                    rule[key] = _date(raw_rule.get(key), f"{field}.{key}")
                if rule["starts_on"] > rule["ends_on"]:
                    raise ValueError(f"{field}.ends_on: precedes starts_on")
            card["rewards"].append(rule)
        for n, raw_benefit in enumerate(_list(raw.get("benefits", []), f"{prefix}.benefits")):
            field = f"{prefix}.benefits[{n}]"
            _mapping(raw_benefit, field)
            card["benefits"].append({
                "name": _text(raw_benefit.get("name"), f"{field}.name"),
                "description": _text(raw_benefit.get("description"), f"{field}.description"),
                "categories": [category_ref(c, f"{field}.categories") for c in
                               _list(raw_benefit.get("categories", []), f"{field}.categories")],
            })
        cards.append(card)
    return {"timezone": timezone, "categories": categories, "cards": cards}


def normalize_category(data: dict, text: str) -> str | None:
    name = text.strip().casefold()
    for category, config in data["categories"].items():
        if name == category or name in config["aliases"]:
            return category
    return None


def recommend(data: dict, category: str, today: date) -> list[dict]:
    results = []
    for card in data["cards"]:
        points = "rewards_program" in card
        rate_field = "points_per_dollar" if points else "cashback_percent"
        active = [rule for rule in card["rewards"] if rule["category"] == category
                  and ("starts_on" not in rule or rule["starts_on"] <= today <= rule["ends_on"])]
        rate = max([card["base_" + rate_field], *[r[rate_field] for r in active]])
        result = {"id": card["id"], "name": card["name"],
                  "reward_percent": rate * CHASE_POINT_VALUE_CENTS if points else rate,
                  "rules": [r for r in active if r[rate_field] == rate],
                  "benefits": [b for b in card["benefits"] if not b["categories"] or category in b["categories"]]}
        if points:
            result["points_per_dollar"] = rate
        results.append(result)
    return sorted(results, key=lambda r: (-r["reward_percent"], r["name"].casefold(), r["id"]))
