#!/usr/bin/env python3
"""Build usage.json from Champions Battle Data's public in-game JSON API.

Keep the existing UI schema; never overwrite the last good snapshot on partial
or stale upstream responses. Run from the repository root.
"""
import concurrent.futures
import datetime as dt
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
BASE = "https://championsbattledata.com"
FORMATS = {"single": "Singles", "double": "Doubles"}
CATEGORIES = {"move": "moves", "held_item": "items", "ability": "abilities",
              "stat_points": "spreads", "stat_alignment": "natures"}
NATURE_MODIFIERS = {
    "Adamant": "+Attack / -Sp. Atk", "Bold": "+Defense / -Attack",
    "Brave": "+Attack / -Speed", "Calm": "+Sp. Def / -Attack",
    "Careful": "+Sp. Def / -Sp. Atk", "Gentle": "+Sp. Def / -Defense",
    "Hasty": "+Speed / -Defense", "Impish": "+Defense / -Sp. Atk",
    "Jolly": "+Speed / -Sp. Atk", "Lax": "+Defense / -Sp. Def",
    "Lonely": "+Attack / -Defense", "Mild": "+Sp. Atk / -Defense",
    "Modest": "+Sp. Atk / -Attack", "Naive": "+Speed / -Sp. Def",
    "Naughty": "+Attack / -Sp. Def", "Quiet": "+Sp. Atk / -Speed",
    "Rash": "+Sp. Atk / -Sp. Def", "Relaxed": "+Defense / -Speed",
    "Sassy": "+Sp. Def / -Speed", "Timid": "+Speed / -Attack",
    "Bashful": "Neutral", "Docile": "Neutral", "Hardy": "Neutral",
    "Quirky": "Neutral", "Serious": "Neutral",
}

def get_json(path):
    url = BASE + path
    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "mz-pokemon-champions-usage/2.0 (community stats cache)",
                "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(attempt + 1)
    raise RuntimeError(f"Could not fetch {url}: {last_error}")

def parse_rows(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("Missing battle rows")
    sections = {v: [] for v in CATEGORIES.values()}
    for row in payload["rows"]:
        if not isinstance(row, dict):
            continue
        category = CATEGORIES.get(str(row.get("category", "")).strip().lower())
        if not category:
            continue
        name = str(row.get("name") or "").strip()
        if category == "spreads":
            keys = ("hp_points", "attack_points", "defense_points", "sp_atk_points", "sp_def_points", "speed_points")
            try:
                name = "/".join(str(int(row[k])) for k in keys)
            except (ValueError, TypeError, KeyError):
                continue
        try:
            pct = float(str(row.get("percentage_value", row.get("percentage", ""))).rstrip("%"))
        except (ValueError, TypeError):
            continue
        if not name or not 0 <= pct <= 100:
            continue
        if category == "natures":
            sections[category].append([name, pct, NATURE_MODIFIERS.get(name, "Neutral")])
        else:
            sections[category].append([name, pct])
    for key in sections:
        sections[key] = sorted(sections[key], key=lambda x: -x[1])[:5 if key == "natures" else 10]
    return sections

def fetch_pokemon(item):
    fmt, entry = item
    name = entry["showdownId"]
    path = "/api/battle/" + fmt + "/" + urllib.parse.quote(name, safe="")
    return name, parse_rows(get_json(path))

def main():
    previous = json.loads((ROOT / "usage.json").read_text(encoding="utf-8"))
    index = get_json("/api")
    entries = index.get("pokemon")
    if not isinstance(entries, list) or len(entries) < 200:
        raise ValueError("Index incomplete; preserving old snapshot")
    names = previous["names"]
    output = {"source": "Pokémon Champions Battle Data · in-game Battle Data",
              "url": BASE + "/api_guide", "names": names, "formats": {}}
    for key, fmt in FORMATS.items():
        ranking = get_json("/api/rankings?format=" + fmt)
        ranked = ranking.get("rankings")
        if not isinstance(ranked, list) or len(ranked) < 200:
            raise ValueError(f"Rankings incomplete: {fmt}")
        lookup = {x.get("showdownId"): x for x in entries if isinstance(x, dict)}
        targets = [(fmt, lookup[x["showdownId"]]) for x in ranked
                   if isinstance(x, dict) and x.get("showdownId") in lookup]
        if len(targets) < 200:
            raise ValueError(f"Too few indexed Pokemon: {fmt}")
        pokemon = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch_pokemon, t): t for t in targets}
            for future in concurrent.futures.as_completed(futures):
                ident, sections = future.result()
                if any(sections.values()):
                    # Match the old MunchStats key convention (Showdown species names).
                    entry = lookup[ident]
                    pokemon[entry.get("showdownName") or entry.get("name") or ident] = sections
        if len(pokemon) < 200:
            raise ValueError(f"Incomplete usage data for {fmt}: {len(pokemon)}")
        for row in ranked:
            if not isinstance(row, dict):
                continue
            name = (lookup.get(row.get("showdownId")) or {}).get("showdownName") or row.get("name")
            if name in pokemon:
                pokemon[name]["rank"] = int(row["position"])
        # Do not claim today's date is the observation date: use the latest dated
        # upstream snapshot when available, otherwise retain a clear unknown label.
        sample = get_json("/api/battle/" + fmt + "/garchomp?days=1")
        daily = sample.get("daily", []) if isinstance(sample, dict) else []
        observed = daily[0].get("date", "") if daily else ""
        try:
            observed = dt.datetime.strptime(observed, "%d_%m_%Y").strftime("%B %d, %Y")
        except ValueError:
            observed = "Unknown (current upstream snapshot)"
        output["formats"][key] = {"updated": observed, "pokemon": pokemon}
    # Fail closed: never replace with a visibly older dated snapshot.
    for key in FORMATS:
        old = previous.get("formats", {}).get(key, {}).get("updated", "")
        new = output["formats"][key]["updated"]
        def date(s):
            try:
                return dt.datetime.strptime(s.split(" at ")[0], "%B %d, %Y")
            except ValueError:
                return None
        if date(old) and date(new) and date(new) < date(old):
            raise ValueError(f"Stale source for {key}: {new} < {old}")
    destination = ROOT / "usage.json"
    serialized = json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n"
    if destination.read_text(encoding="utf-8") != serialized:
        destination.write_text(serialized, encoding="utf-8")
        print("Updated usage data:", [(k, len(v["pokemon"]), v["updated"]) for k, v in output["formats"].items()])
    else:
        print("No new battle data")

if __name__ == "__main__":
    main()
