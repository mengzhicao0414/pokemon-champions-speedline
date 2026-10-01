#!/usr/bin/env python3
"""Refresh the public, in-game Champions usage snapshot for GitHub Pages."""

import gzip
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/mobile-packs/stats/champions/"
FORMATS = {"single": "championssingles", "double": "championsdoubles"}
CATEGORIES = {"moves": "moves_list", "spreads": "spreads_list", "items": "items_list", "abilities": "abilities_list"}


def fetch_pack(format_code):
    request = urllib.request.Request(BASE + format_code + ".json.gz", headers={"User-Agent": "pokemon-champions-speedline/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        pack = json.loads(gzip.decompress(response.read()))
    if pack.get("format") != format_code or pack.get("category") != "in_game" or pack.get("value_kind") != "rank":
        raise ValueError(f"Unexpected pack: {format_code}")
    if len(pack.get("pokemon", {})) < 100:
        raise ValueError(f"Incomplete pack: {format_code}")
    return pack


def top_ten(entries):
    result = []
    for entry in entries or []:
        if not isinstance(entry, list) or len(entry) < 2 or not entry[0]:
            continue
        try:
            percentage = float(str(entry[1]).rstrip("%"))
        except (TypeError, ValueError):
            continue
        if not 0 <= percentage <= 100:
            continue
        result.append([str(entry[0]), percentage])
    return sorted(result, key=lambda row: -row[1])[:10]


def top_natures(entries):
    """Keep the in-game nature modifier next to the ranked percentage."""
    result = []
    for entry in entries or []:
        if not isinstance(entry, list) or len(entry) < 3 or not entry[0]:
            continue
        try:
            percentage = float(str(entry[1]).rstrip("%"))
        except (TypeError, ValueError):
            continue
        modifier = str(entry[2])
        if not 0 <= percentage <= 100 or not (modifier == "Neutral" or (modifier.startswith("+") and " / -" in modifier)):
            continue
        result.append([str(entry[0]), percentage, modifier])
    return sorted(result, key=lambda row: -row[1])[:5]


def main():
    # Fetch both first; an upstream failure must not overwrite yesterday's usable snapshot.
    packs = {kind: fetch_pack(code) for kind, code in FORMATS.items()}
    names = json.loads((ROOT / "usage_names.json").read_text(encoding="utf-8"))
    output = {"source": "MunchStats · Pokémon Champions in-game Battle Data", "url": "https://www.munchstats.com/about/", "names": names, "formats": {}}
    for kind, pack in packs.items():
        pokemon = {}
        for name, detail in pack["pokemon"].items():
            sections = {key: top_ten(detail.get(field)) for key, field in CATEGORIES.items()}
            sections["natures"] = top_natures(detail.get("natures_list"))
            try:
                rank = int(str(detail.get("rank", "")).lstrip("#"))
            except (TypeError, ValueError):
                rank = 0
            if rank > 0:
                sections["rank"] = rank
            if any(sections.values()):
                pokemon[name] = sections
        output["formats"][kind] = {"updated": pack.get("updated", ""), "pokemon": pokemon}
    destination = ROOT / "usage.json"
    new = json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n"
    if not destination.exists() or destination.read_text(encoding="utf-8") != new:
        destination.write_text(new, encoding="utf-8")
        print("Updated", destination, "; singles/doubles:", *(len(output["formats"][x]["pokemon"]) for x in FORMATS))
    else:
        print("No new battle data")


if __name__ == "__main__":
    main()
