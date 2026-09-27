#!/usr/bin/env python3
"""Build the local, offline reference text used by the usage popup.

PokeAPI's Chinese text covers older games. For newer moves we retain its
English wording instead of inventing a Chinese description.
"""

import csv
import io
import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"


def rows(filename):
    with urllib.request.urlopen(BASE + filename, timeout=45) as response:
        return list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))


def names(filename, key):
    return {row["name"]: row[key] for row in rows(filename) if row["local_language_id"] == "9"}


def flavor(filename, key):
    found = {}
    for row in rows(filename):
        if row["language_id"] not in {"9", "12"}:
            continue
        id_ = row[key]
        language = row["language_id"]
        current = found.get((id_, language))
        if current is None or int(row["version_group_id"]) > current[0]:
            found[(id_, language)] = (int(row["version_group_id"]), row["flavor_text"])
    return {key: re.sub(r"\s*\n\s*", "", value[1]).strip() for key, value in found.items()}


def description(flavor_text, id_):
    if (id_, "12") in flavor_text:
        return flavor_text[(id_, "12")], "zh"
    if (id_, "9") in flavor_text:
        return flavor_text[(id_, "9")], "en"
    return "", ""


def main():
    used = json.loads((ROOT / "usage_names.json").read_text(encoding="utf-8"))
    move_ids = names("move_names.csv", "move_id")
    item_ids = names("item_names.csv", "item_id")
    ability_ids = names("ability_names.csv", "ability_id")
    move_flavor = flavor("move_flavor_text.csv", "move_id")
    item_flavor = flavor("item_flavor_text.csv", "item_id")
    ability_flavor = flavor("ability_flavor_text.csv", "ability_id")
    move_stats = {row["id"]: row for row in rows("moves.csv")}
    type_names = {row["type_id"]: row["name"] for row in rows("type_names.csv") if row["local_language_id"] == "12"}
    damage_classes = {"1": "变化", "2": "物理", "3": "特殊"}

    # The page already contains Champions-specific ability text, which takes
    # precedence over text from previous main-series games.
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    ability_data = json.loads(re.search(r"const abilityData=(\{.*?\});\nconst abilityDialog", html, re.S).group(1))
    champions_abilities = {value[0]: value[1].replace("\n", "") for value in ability_data.values()}

    result = {"moves": {}, "items": {}, "abilities": {}}
    for english, chinese in used["moves"].items():
        id_ = move_ids.get(english)
        if not id_ and english not in {"Forest's Curse", "King's Shield"}:
            continue
        info = move_stats.get(id_, {})
        desc, lang = description(move_flavor, id_)
        if english == "Forest's Curse":
            desc, lang = "使对手追加草属性。", "zh"
        elif english == "King's Shield":
            desc, lang = "防住对手的攻击。若防住接触类招式，会降低对手的攻击。", "zh"
        result["moves"][english] = {
            "description": desc,
            "language": lang,
            "type": type_names.get(info.get("type_id"), ""),
            "category": damage_classes.get(info.get("damage_class_id"), ""),
            "power": info.get("power", ""),
            "accuracy": info.get("accuracy", ""),
            "pp": info.get("pp", ""),
        }
    for english, chinese in used["items"].items():
        id_ = item_ids.get(english)
        desc, lang = description(item_flavor, id_) if id_ else ("", "")
        if not desc and "进化石" in chinese:
            pokemon = chinese.split("进化石", 1)[0]
            desc, lang = f"让{pokemon}携带后，在战斗中可以进行超级进化。", "zh"
        elif english == "Fairy Feather":
            desc, lang = "携带后，妖精属性招式的威力会提高。", "zh"
        elif english == "King's Rock":
            desc, lang = "携带后，使用能造成伤害的招式时，有时会让对手畏缩。", "zh"
        result["items"][english] = {"description": desc, "language": lang}
    for english, chinese in used["abilities"].items():
        id_ = ability_ids.get(english)
        desc, lang = description(ability_flavor, id_) if id_ else ("", "")
        if chinese in champions_abilities:
            desc, lang = champions_abilities[chinese], "zh"
        result["abilities"][english] = {"description": desc, "language": lang}

    path = ROOT / "details.json"
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    for key, entries in result.items():
        print(key, len(entries), "described", sum(bool(item["description"]) for item in entries.values()),
              "English fallback", sum(item["language"] == "en" for item in entries.values()))


if __name__ == "__main__":
    main()
