#!/usr/bin/env python3
"""Build reference text and Champions learnsets for the site.

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
CHAMPIONS = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/mods/champions/"
MOVE_TARGETS = {
    "1": "根据反击条件决定", "2": "指定单体", "3": "一名队友",
    "4": "己方场地", "5": "自己或一名队友", "6": "对方场地",
    "7": "自己", "8": "随机一名对手", "9": "场上其他全部（含队友）",
    "10": "指定单体", "11": "对方全体", "12": "全场场地",
    "13": "己方全体（含自己）", "14": "场上全体（含自己）",
    "15": "所有队友", "16": "己方濒死宝可梦",
}
CHAMPIONS_TARGETS = {"adjacentAllyOrSelf": "自己或一名队友"}


def rows(filename):
    with urllib.request.urlopen(BASE + filename, timeout=45) as response:
        return list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))


def names(filename, key):
    return {row["name"]: row[key] for row in rows(filename) if row["local_language_id"] == "9"}


def identifier(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def champions_entries(filename):
    with urllib.request.urlopen(CHAMPIONS + filename, timeout=45) as response:
        source = response.read().decode("utf-8")
    return {key: body for key, body in re.findall(r"^\t([a-z0-9]+): \{\n([\s\S]*?)^\t\},", source, re.M)}


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
    move_name_rows = rows("move_names.csv")
    move_ids = {row["name"]: row["move_id"] for row in move_name_rows if row["local_language_id"] == "9"}
    english_by_id = {row["move_id"]: row["name"] for row in move_name_rows if row["local_language_id"] == "9"}
    chinese_by_id = {row["move_id"]: row["name"] for row in move_name_rows if row["local_language_id"] == "12"}
    move_by_identifier = {identifier(english): english for english in move_ids}
    move_by_identifier.update({identifier(english): english for english in used["moves"]})
    id_by_identifier = {identifier(english): id_ for english, id_ in move_ids.items()}
    champions_learnsets = champions_entries("learnsets.ts")
    champions_moves = champions_entries("moves.ts")
    all_move_identifiers = set()
    learned = {}
    for species, body in champions_learnsets.items():
        pool = re.search(r"\t\tlearnset: \{([\s\S]*?)\t\t\},", body)
        if not pool:
            raise ValueError("Missing Champions learnset for " + species)
        move_keys = re.findall(r"^\t\t\t([a-z0-9]+): \[", pool.group(1), re.M)
        if not move_keys:
            raise ValueError("Empty Champions learnset for " + species)
        all_move_identifiers.update(move_keys)
        learned[species] = [move_by_identifier.get(key, key) for key in move_keys]
    if len(learned) < 250 or not all_move_identifiers <= id_by_identifier.keys():
        raise ValueError("Champions learnset is incomplete or includes unknown moves")
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
    all_english_moves = set(used["moves"]) | {move_by_identifier[key] for key in all_move_identifiers}
    for english in sorted(all_english_moves):
        id_ = move_ids.get(english) or id_by_identifier.get(identifier(english))
        if not id_ and english not in {"Forest's Curse", "King's Shield"}:
            continue
        info = move_stats.get(id_, {})
        desc, lang = description(move_flavor, id_)
        if english == "Forest's Curse":
            desc, lang = "使对手追加草属性。", "zh"
        elif english == "King's Shield":
            desc, lang = "防住对手的攻击。若防住接触类招式，会降低对手的攻击。", "zh"
        override = champions_moves.get(identifier(english), "")
        def changed(field, default):
            match = re.search(r"^\s*" + field + r":\s*(\d+),", override, re.M)
            return match.group(1) if match else default
        new_type = re.search(r'^\s*type:\s*"([^"]+)",', override, re.M)
        new_target = re.search(r'^\s*target:\s*"([^"]+)",', override, re.M)
        target = MOVE_TARGETS.get(info.get("target_id"), "")
        if new_target:
            target = CHAMPIONS_TARGETS.get(new_target.group(1))
            if not target:
                raise ValueError("Unknown Champions move target: " + new_target.group(1))
        if english == "Dragon Darts":
            target = "对方两只各1次；仅一只则2次"
        type_name = type_names.get(info.get("type_id"), "")
        if new_type:
            known_types = {row["name"].lower():row["type_id"] for row in rows("type_names.csv") if row["local_language_id"] == "9"}
            chinese_types = {row["type_id"]:row["name"] for row in rows("type_names.csv") if row["local_language_id"] == "12"}
            type_name = chinese_types.get(known_types.get(new_type.group(1).lower()), type_name)
        result["moves"][english] = {
            "name": chinese_by_id.get(id_, used["moves"].get(english, english)),
            "description": desc,
            "language": lang,
            "type": type_name,
            "category": damage_classes.get(info.get("damage_class_id"), ""),
            "target": target,
            "power": changed("basePower", info.get("power", "")),
            "accuracy": changed("accuracy", info.get("accuracy", "")),
            "pp": changed("pp", info.get("pp", "")),
        }
    cards = re.findall(r'<article id="([^"]+)" class="card" data-usage-key="([^"]+)"', html)
    aliases = {"gourgeistsmall":"gourgeist", "gourgeistlarge":"gourgeist", "gourgeistsuper":"gourgeist", "vivillonfancy":"vivillon"}
    card_pools = {}
    for card_id, english in cards:
        key = aliases.get(identifier(english), identifier(english))
        if key not in learned:
            raise ValueError("Missing Champions learnset for card " + card_id + ": " + english)
        card_pools[card_id] = key
    (ROOT / "learnsets.json").write_text(json.dumps({
        "source": "https://github.com/smogon/pokemon-showdown/blob/master/data/mods/champions/learnsets.ts",
        "pokemon": learned, "cards": card_pools
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
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
