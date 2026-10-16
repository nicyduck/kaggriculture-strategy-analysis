#!/usr/bin/env python3
"""Turn replay traces into a compact, falsifiable strategy model.

Unlike ``audit_replays.py`` (which checks accounting), this program searches
for invariants, branch points, spatial templates, crop phases, and worker
specialisation.  It does not pretend to recover the original source code;
the output is the smallest policy consistent with the observed games.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_replays import ANIMALS, load_replays


MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
ANIMAL_OPS = {"FEED", "CARE", "COLLECT_FERTILIZER"}
CROP_OPS = {"WATER", "FERTILIZE"}


def player_index(replay, team):
    return replay["info"]["TeamNames"].index(team)


def animals(observation, player):
    result = Counter()
    for row in observation["farms"][player]["tiles"]:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal"):
                result[tile["animal"]] += 1
    for animal in ANIMALS:
        result[animal] += int(observation["private"]["shed"].get(animal, 0))
        result[animal] += sum(int(i.get(animal, 0)) for i in observation["private"]["inventories"])
    return result


def successful_plant(before, after):
    return before is None and isinstance(after, dict) and after.get("kind") == "PLANT"


def classify_role(operation):
    if operation in MOVES:
        return "move"
    if operation in ANIMAL_OPS:
        return "animal"
    if operation in CROP_OPS:
        return "crop_care"
    if operation in {"PLANT", "DIG"}:
        return "crop_renewal"
    if operation == "HARVEST":
        return "harvest"
    if operation in {"PICKUP", "DROP"}:
        return "logistics"
    return operation.lower()


def region(position):
    x, y = position
    return ("N" if y < 5 else "S") + ("W" if x < 5 else "E")


def analyze(replays, team):
    episodes = []
    plant_by_day = Counter()
    fertilize_by_day = Counter()
    role_ops = defaultdict(Counter)
    role_regions = defaultdict(Counter)
    placements = defaultdict(Counter)

    for _, replay in replays:
        player = player_index(replay, team)
        episode_id = replay["info"]["EpisodeId"]
        steps = replay["steps"]
        purchase_events = []
        placed_seen = set()
        previous_animals = animals(steps[0][player]["observation"], player)

        for t in range(1, len(steps)):
            before = steps[t - 1][player]["observation"]
            after = steps[t][player]["observation"]
            action = steps[t][player].get("action") or {}
            commands = [action.get("farmer", ["PASS"])] + list(action.get("hands", []))
            positions = [before["farms"][player]["farmer"]] + list(before["farms"][player]["hands"])
            used_effects = set()

            current_animals = animals(after, player)
            added = {a: current_animals[a] - previous_animals[a] for a in ANIMALS
                     if current_animals[a] > previous_animals[a]}
            if added:
                purchase_events.append({"day": after["day"], "step": t, "animals": added})
            previous_animals = current_animals

            for actor, command in enumerate(commands):
                if not command or actor >= len(positions):
                    continue
                operation = command[0]
                x, y = positions[actor]
                old_tile = before["farms"][player]["tiles"][y][x]
                new_tile = after["farms"][player]["tiles"][y][x]

                if after["day"] >= 10:
                    role_ops[actor][classify_role(operation)] += 1
                    role_regions[actor][region((x, y))] += 1

                effect = (x, y, operation)
                if effect in used_effects:
                    continue
                if operation == "PLANT" and successful_plant(old_tile, new_tile):
                    plant_by_day[(after["day"], new_tile["crop"])] += 1
                    used_effects.add(effect)
                elif (operation == "FERTILIZE" and isinstance(old_tile, dict)
                      and old_tile.get("kind") == "PLANT" and isinstance(new_tile, dict)
                      and int(new_tile.get("fertilized_until_day", -1))
                      > int(old_tile.get("fertilized_until_day", -1))):
                    fertilize_by_day[(after["day"], old_tile["crop"])] += 1
                    used_effects.add(effect)

            for y, row in enumerate(after["farms"][player]["tiles"]):
                for x, tile in enumerate(row):
                    if not isinstance(tile, dict) or not tile.get("animal"):
                        continue
                    key = (x, y, tile["animal"], tile.get("placed_day"))
                    if key not in placed_seen:
                        placed_seen.add(key)
                        placements[(x, y)][tile["animal"]] += 1

        day6_shops = Counter(steps[6 * 24][player]["observation"]["town"]["unlocked_shops"])
        day6_added = Counter()
        for event in purchase_events:
            if event["day"] == 6:
                day6_added.update(event["animals"])
        if day6_shops["YARN_STORE"]:
            branch = "SHEEP"
        elif day6_added["GOOSE"] >= 4:
            branch = "GOOSE"
        elif day6_added["GOOSE"] == 0:
            branch = "COW"
        else:
            branch = "BALANCED"
        episodes.append({
            "episode_id": episode_id,
            "day6_shops": dict(day6_shops),
            "day6_branch": branch,
            "day6_animals_added": dict(day6_added),
            "peak_animals": dict(max((animals(s[player]["observation"], player) for s in steps),
                                     key=lambda c: sum(c.values()))),
            "purchase_events": purchase_events,
        })

    workers = []
    for actor in sorted(role_ops):
        non_move = role_ops[actor].copy()
        del non_move["move"]
        workers.append({
            "actor": actor,
            "primary_role": non_move.most_common(1)[0][0] if non_move else "unknown",
            "primary_region": role_regions[actor].most_common(1)[0][0],
            "operations": dict(role_ops[actor]),
            "regions": dict(role_regions[actor]),
        })

    return {
        "episodes": episodes,
        "plant_by_day": [{"day": d, "crop": c, "count": n}
                         for (d, c), n in sorted(plant_by_day.items())],
        "fertilize_by_day": [{"day": d, "crop": c, "count": n}
                             for (d, c), n in sorted(fertilize_by_day.items())],
        "animal_coordinate_templates": [
            {"x": x, "y": y, "animals": dict(counts)}
            for (x, y), counts in sorted(placements.items(), key=lambda i: (i[0][1], i[0][0]))
        ],
        "mature_worker_roles": workers,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="RAW zip, replay directory, or replay JSON glob")
    parser.add_argument("--team", default="Majkel1337")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(load_replays(args.inputs), args.team)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {len(result['episodes'])} episodes")


if __name__ == "__main__":
    main()
