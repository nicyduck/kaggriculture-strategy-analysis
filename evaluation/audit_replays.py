#!/usr/bin/env python3
"""Audit Kaggriculture replays by reconciling issued actions with state changes.

Kaggle replay step ``t`` stores the action whose result is already visible in
the observation at step ``t``.  Successful unit actions are therefore inferred
from the transition ``observation[t - 1] -> observation[t]``.
"""

import argparse
import csv
import glob
import json
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
ANIMALS = ("COW", "SHEEP", "GOOSE")
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
LAND_COSTS = {"NE": 1000, "SW": 2000, "SE": 4000}
ANIMAL_PRODUCTS = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}


def private_total(observation, item):
    private = observation["private"]
    return int(private["shed"].get(item, 0)) + sum(
        int(inv.get(item, 0)) for inv in private["inventories"]
    )


def board_animal_count(observation, player, animal):
    return sum(
        isinstance(tile, dict) and tile.get("animal") == animal
        for row in observation["farms"][player]["tiles"] for tile in row
    )


def owned_animal_count(observation, player, animal):
    return board_animal_count(observation, player, animal) + private_total(observation, animal)


def tile_at(observation, player, position):
    x, y = position
    return observation["farms"][player]["tiles"][y][x]


def item_delta(previous, current, item):
    return private_total(current, item) - private_total(previous, item)


def load_replays(inputs):
    replays = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            files = sorted(path.glob("**/*-replay.json"))
            replays.extend((str(p), json.loads(p.read_text(encoding="utf-8"))) for p in files)
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for name in sorted(archive.namelist()):
                    if name.endswith("-replay.json"):
                        replays.append((f"{path}!{name}", json.loads(archive.read(name))))
        else:
            matches = sorted(glob.glob(raw))
            if not matches and path.exists():
                matches = [str(path)]
            for match in matches:
                p = Path(match)
                replays.append((str(p), json.loads(p.read_text(encoding="utf-8"))))
    if not replays:
        raise SystemExit("No replay JSON files found")
    return replays


def find_player(replay, team, player):
    if player is not None:
        return player
    names = replay.get("info", {}).get("TeamNames", [])
    if team not in names:
        raise ValueError(f"team {team!r} not present in {names!r}")
    return names.index(team)


def command_result(op, previous, current, before_tile, after_tile, before_inv, after_inv):
    if op in MOVES:
        return previous != current
    if op == "PASS":
        return True
    if op == "BUILD_PASTURE":
        return before_tile is None and isinstance(after_tile, dict) and after_tile.get("kind") == "PASTURE"
    if op == "BUILD_COOP":
        return before_tile is None and isinstance(after_tile, dict) and after_tile.get("kind") == "COOP"
    if op == "PLANT":
        return before_tile is None and isinstance(after_tile, dict) and after_tile.get("kind") == "PLANT"
    if op == "WATER":
        return (
            isinstance(before_tile, dict) and before_tile.get("kind") == "PLANT"
            and isinstance(after_tile, dict) and after_tile.get("kind") == "PLANT"
            and bool(after_tile.get("watered_today"))
        )
    if op == "FEED":
        return (
            isinstance(before_tile, dict) and before_tile.get("animal")
            and isinstance(after_tile, dict) and after_tile.get("animal")
            and bool(after_tile.get("fed_today"))
        )
    if op == "CARE":
        return (
            isinstance(before_tile, dict) and before_tile.get("animal")
            and isinstance(after_tile, dict) and after_tile.get("animal")
            and bool(after_tile.get("cared_today"))
        )
    if op == "COLLECT_FERTILIZER":
        return (
            isinstance(before_tile, dict) and before_tile.get("animal")
            and before_tile.get("fertilizer_available")
            and isinstance(after_tile, dict) and not after_tile.get("fertilizer_available")
        )
    if op == "HARVEST":
        if not isinstance(before_tile, dict):
            return False
        if before_tile.get("kind") == "PLANT":
            return after_tile is None or (
                isinstance(after_tile, dict)
                and after_tile.get("kind") == "PLANT"
                and int(after_tile.get("yield_units", 0)) < int(before_tile.get("yield_units", 0))
            )
        if before_tile.get("animal"):
            return isinstance(after_tile, dict) and int(after_tile.get("yield_units", 0)) < int(before_tile.get("yield_units", 0))
        return False
    if op == "DIG":
        return before_tile is not None and after_tile is None
    if op == "FERTILIZE":
        return (
            isinstance(before_tile, dict) and before_tile.get("kind") == "PLANT"
            and isinstance(after_tile, dict)
            and int(after_tile.get("fertilized_until_day", -1)) > int(before_tile.get("fertilized_until_day", -1))
        )
    if op == "PICKUP":
        return sum(after_inv.values()) > sum(before_inv.values())
    if op == "DROP":
        return sum(after_inv.values()) < sum(before_inv.values())
    if op == "PLACE":
        return (
            isinstance(after_tile, dict) and after_tile.get("animal")
            and not (isinstance(before_tile, dict) and before_tile.get("animal"))
        ) or sum(after_inv.values()) < sum(before_inv.values())
    return False


def transition_events(replay, player):
    steps = replay["steps"]
    events = []
    ledgers = []
    counters = Counter()
    purchase_requested = Counter()
    purchase_inferred = Counter()
    sold_requested = Counter()
    sold_inferred = Counter()
    hires_inferred = 0
    daily_money = []
    actual_land = []
    max_shed = 0
    max_crops = Counter()
    max_animals = Counter()
    feed_miss_days = set()
    water_miss_days = set()

    for day in range(30):
        step = min(day * 24, len(steps) - 1)
        daily_money.append(float(steps[step][player]["observation"]["farms"][player]["money"]))
    daily_money.append(float(steps[-1][player]["observation"]["farms"][player]["money"]))

    for t, state in enumerate(steps):
        observation = state[player]["observation"]
        farm = observation["farms"][player]
        max_shed = max(max_shed, sum(int(v) for v in observation["private"]["shed"].values()))
        current_crops = Counter()
        current_animals = Counter()
        for row in farm["tiles"]:
            for tile in row:
                if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    current_crops[tile["crop"]] += 1
                    if int(tile.get("consecutive_unwatered", 0)):
                        water_miss_days.add(int(observation["day"]))
                elif isinstance(tile, dict) and tile.get("animal"):
                    current_animals[tile["animal"]] += 1
                    if int(tile.get("consecutive_unfed", 0)):
                        feed_miss_days.add(int(observation["day"]))
        for item, value in current_crops.items():
            max_crops[item] = max(max_crops[item], value)
        for item, value in current_animals.items():
            max_animals[item] = max(max_animals[item], value)

        if t == 0:
            continue
        previous = steps[t - 1][player]["observation"]
        current = observation
        action = state[player].get("action") or {}
        commands = [action.get("farmer", ["PASS"])] + list(action.get("hands", []))
        before_positions = [previous["farms"][player]["farmer"]] + list(previous["farms"][player].get("hands", []))
        after_positions = [current["farms"][player]["farmer"]] + list(current["farms"][player].get("hands", []))
        before_inventories = previous["private"]["inventories"]
        after_inventories = current["private"]["inventories"]
        successful_harvest = Counter()
        successful_feed = 0
        successful_collect = 0
        successful_fertilize = 0
        successful_drop = 0
        successful_plants = Counter()
        consumed_tile_effects = set()

        for actor, command in enumerate(commands):
            if not command:
                command = ["PASS"]
            op = command[0]
            counters[f"unit_issued:{op}"] += 1
            if actor >= len(before_positions):
                counters[f"unit_unmatched:{op}"] += 1
                continue
            before_pos = before_positions[actor]
            after_pos = after_positions[actor] if actor < len(after_positions) else before_pos
            before_tile = tile_at(previous, player, before_pos)
            after_tile = tile_at(current, player, before_pos)
            before_inv = before_inventories[actor] if actor < len(before_inventories) else {}
            after_inv = after_inventories[actor] if actor < len(after_inventories) else {}
            success = command_result(op, before_pos, after_pos, before_tile, after_tile, before_inv, after_inv)
            # A single tile transition can satisfy only one simultaneous unit
            # command.  Without this guard, co-located actors double-count one
            # harvest/feed/collection state change.
            tile_effect_key = (tuple(before_pos), op)
            if success and op not in MOVES | {"PASS", "PICKUP", "DROP"}:
                if tile_effect_key in consumed_tile_effects:
                    success = False
                else:
                    consumed_tile_effects.add(tile_effect_key)
            # End-of-day refresh can reset WATER/FEED/CARE immediately after a
            # valid action.  Record these as ambiguous rather than invalid.
            ambiguous = int(current["hour"]) == 0 and op in {"WATER", "FEED", "CARE"}
            outcome = "success" if success else ("ambiguous" if ambiguous else "no_effect")
            counters[f"unit_{outcome}:{op}"] += 1
            events.append({
                "episode_id": replay.get("info", {}).get("EpisodeId"),
                "step": t,
                "day": int(current["day"]),
                "player": player,
                "actor": actor,
                "category": "unit",
                "operation": op,
                "outcome": outcome,
                "x": before_pos[0],
                "y": before_pos[1],
                "detail": json.dumps(command[1:], separators=(",", ":")),
            })
            if success and op == "PLANT" and len(command) > 1:
                successful_plants[command[1]] += 1
            if success and op == "FEED":
                successful_feed += 1
            if success and op == "COLLECT_FERTILIZER":
                successful_collect += 1
            if success and op == "FERTILIZE":
                successful_fertilize += 1
            if success and op == "DROP":
                successful_drop += 1
            if success and op == "HARVEST" and isinstance(before_tile, dict):
                if before_tile.get("kind") == "PLANT":
                    successful_harvest[before_tile.get("crop")] += int(before_tile.get("yield_units", 0))
                elif before_tile.get("animal"):
                    successful_harvest[ANIMAL_PRODUCTS[before_tile["animal"]]] += int(before_tile.get("yield_units", 0))

        previous_unlocked = set(previous["farms"][player].get("unlocked_quadrants", []))
        current_unlocked = set(current["farms"][player].get("unlocked_quadrants", []))
        newly_unlocked = sorted(current_unlocked - previous_unlocked)
        if newly_unlocked:
            actual_land.extend((int(current["day"]), t, quadrant) for quadrant in newly_unlocked)
            counters["market_success:BUY_LAND"] += len(newly_unlocked)

        previous_hands = len(previous["farms"][player].get("hands", []))
        current_hands = len(current["farms"][player].get("hands", []))
        if int(current["day"]) != int(previous["day"]):
            successful_hires = current_hands
        else:
            successful_hires = max(0, current_hands - previous_hands)
        hires_inferred += successful_hires
        counters["market_success:HIRE"] += successful_hires

        market = action.get("market", [])
        requested = Counter()
        for index, order in enumerate(market):
            if not order:
                continue
            op = order[0]
            counters[f"market_issued:{op}"] += 1
            item = order[1] if len(order) > 1 else ""
            quantity = int(order[2]) if len(order) > 2 else 1
            if op.startswith("BUY_") and item:
                requested[item] += quantity
                purchase_requested[item] += quantity
            elif op == "SELL":
                sold_requested[item] += quantity
            events.append({
                "episode_id": replay.get("info", {}).get("EpisodeId"),
                "step": t,
                "day": int(current["day"]),
                "player": player,
                "actor": index,
                "category": "market",
                "operation": op,
                "outcome": "issued",
                "x": "",
                "y": "",
                "detail": json.dumps(order[1:], separators=(",", ":")),
            })

        for animal in ANIMALS:
            before_owned = owned_animal_count(previous, player, animal)
            after_owned = owned_animal_count(current, player, animal)
            removed = 0
            for y in range(len(previous["farms"][player]["tiles"])):
                for x in range(len(previous["farms"][player]["tiles"][y])):
                    before_tile = previous["farms"][player]["tiles"][y][x]
                    after_tile = current["farms"][player]["tiles"][y][x]
                    if (
                        isinstance(before_tile, dict) and before_tile.get("animal") == animal
                        and not (isinstance(after_tile, dict) and after_tile.get("animal") == animal)
                    ):
                        removed += 1
                        counters[f"animal_removed:{animal}"] += 1
            inferred = after_owned - before_owned + removed
            if inferred > 0:
                purchase_inferred[animal] += inferred

        for crop in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"):
            seed_delta = int(current["private"]["seeds"].get(crop, 0)) - int(previous["private"]["seeds"].get(crop, 0))
            inferred = seed_delta + successful_plants[crop]
            if inferred > 0:
                purchase_inferred[crop] += inferred

        # Product ledger.  Positive residual is inferred market buying or an
        # unobserved harvest; negative residual is possible overflow/loss.
        for item in PRODUCTS:
            delta = item_delta(previous, current, item)
            harvest = successful_harvest[item]
            collect = successful_collect if item == "FERTILIZER" else 0
            consume = successful_fertilize if item == "FERTILIZER" else 0
            feed = successful_feed if item == "WHEAT" else 0
            requested_sell = sum(
                int(order[2]) for order in market
                if order and order[0] == "SELL" and order[1] == item
            )
            available_to_sell = int(previous["private"]["shed"].get(item, 0))
            actual_sell = min(requested_sell, available_to_sell)
            sold_inferred[item] += actual_sell
            inferred_buy_or_residual = delta - harvest - collect + consume + feed + actual_sell
            if item == "WHEAT" and inferred_buy_or_residual > 0:
                purchase_inferred[item] += inferred_buy_or_residual
            unexplained_loss = max(0, -inferred_buy_or_residual)
            loss_class = ""
            if unexplained_loss:
                expired_hand_inventory = sum(
                    int(inv.get(item, 0)) for inv in previous["private"]["inventories"][1:]
                )
                if int(current["hour"]) == 0 and expired_hand_inventory > 0:
                    loss_class = "hand_expiry"
                elif successful_drop:
                    loss_class = "drop_overflow"
                else:
                    loss_class = "unexplained"
                counters[f"inventory_loss_{loss_class}:{item}"] += unexplained_loss
            if delta or harvest or collect or feed or actual_sell or inferred_buy_or_residual:
                ledgers.append({
                    "episode_id": replay.get("info", {}).get("EpisodeId"),
                    "step": t,
                    "day": int(current["day"]),
                    "item": item,
                    "private_delta": delta,
                    "harvested": harvest,
                    "collected": collect,
                    "consumed": consume,
                    "fed": feed,
                    "sold_inferred": actual_sell,
                    "bought_or_residual": inferred_buy_or_residual,
                    "unexplained_loss": unexplained_loss,
                    "loss_class": loss_class,
                })

    final_observation = steps[-1][player]["observation"]
    final_money = float(final_observation["farms"][player]["money"])
    reward = float(replay["rewards"][player])
    return {
        "events": events,
        "ledgers": ledgers,
        "summary": {
            "episode_id": replay.get("info", {}).get("EpisodeId"),
            "seed": replay.get("info", {}).get("seed"),
            "player": player,
            "team": replay.get("info", {}).get("TeamNames", [None, None])[player],
            "opponent": replay.get("info", {}).get("TeamNames", [None, None])[1 - player],
            "final_money": final_money,
            "reward": reward,
            "money_reconciled": final_money == reward and abs(sum(
                float(steps[t][player]["observation"]["farms"][player]["money"])
                - float(steps[t - 1][player]["observation"]["farms"][player]["money"])
                for t in range(1, len(steps))
            ) - (final_money - float(steps[0][player]["observation"]["farms"][player]["money"]))) < 1e-9,
            "daily_money": daily_money,
            "actual_land": actual_land,
            "max_shed": max_shed,
            "peak_crops": dict(max_crops),
            "peak_animals": dict(max_animals),
            "feed_miss_days": sorted(feed_miss_days),
            "water_miss_days": sorted(water_miss_days),
            "issued_purchases": dict(purchase_requested),
            "inferred_purchases": dict(purchase_inferred),
            "issued_sales": dict(sold_requested),
            "inferred_sales": dict(sold_inferred),
            "inferred_hires": hires_inferred,
            "counters": dict(sorted(counters.items())),
        },
    }


def verify_steps_csv(path, replays):
    expected = {}
    for _, replay in replays:
        episode_id = int(replay.get("info", {}).get("EpisodeId"))
        expected[episode_id] = replay
    counts = Counter()
    mismatches = Counter()
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            episode_id = int(row["episode_id"])
            step = int(row["step"])
            player = int(row["player"])
            counts[episode_id] += 1
            replay = expected.get(episode_id)
            if replay is None or step >= len(replay["steps"]):
                mismatches["missing_replay_step"] += 1
                continue
            state = replay["steps"][step][player]
            if json.loads(row["action_json"]) != state.get("action"):
                mismatches["action"] += 1
            if json.loads(row["observation_json"]) != state.get("observation"):
                mismatches["observation"] += 1
            if float(row["reward"]) != float(state.get("reward", 0)):
                mismatches["reward"] += 1
            if row["status"] != state.get("status"):
                mismatches["status"] += 1
    return {
        "rows_by_episode": dict(sorted(counts.items())),
        "mismatches": dict(sorted(mismatches.items())),
        "complete": not mismatches and all(counts[eid] == 1440 for eid in expected),
    }


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Replay files, directories, globs, or RAW zip archives")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--team", help="Team name used to select the audited player")
    selection.add_argument("--player", type=int, choices=(0, 1), help="Fixed player index")
    parser.add_argument("--steps-csv", help="Optional exported step CSV to compare byte-for-structure")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()

    replays = load_replays(args.inputs)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    episode_rows = []
    event_rows = []
    ledger_rows = []
    aggregate = Counter()
    for source, replay in replays:
        player = find_player(replay, args.team, args.player)
        result = transition_events(replay, player)
        summary = result["summary"]
        summary["source"] = source
        episode_rows.append(summary)
        event_rows.extend(result["events"])
        ledger_rows.extend(result["ledgers"])
        aggregate.update(summary["counters"])

    csv_check = verify_steps_csv(args.steps_csv, replays) if args.steps_csv else None
    compact_rows = []
    for row in episode_rows:
        compact_rows.append({
            "episode_id": row["episode_id"],
            "seed": row["seed"],
            "player": row["player"],
            "team": row["team"],
            "opponent": row["opponent"],
            "final_money": row["final_money"],
            "reward": row["reward"],
            "money_reconciled": row["money_reconciled"],
            "max_shed": row["max_shed"],
            "actual_land": json.dumps(row["actual_land"], separators=(",", ":")),
            "peak_animals": json.dumps(row["peak_animals"], sort_keys=True, separators=(",", ":")),
            "peak_crops": json.dumps(row["peak_crops"], sort_keys=True, separators=(",", ":")),
            "feed_miss_days": json.dumps(row["feed_miss_days"], separators=(",", ":")),
            "water_miss_days": json.dumps(row["water_miss_days"], separators=(",", ":")),
        })

    summary = {
        "replays": len(episode_rows),
        "team": args.team,
        "all_money_reconciled": all(row["money_reconciled"] for row in episode_rows),
        "mean_final_money": statistics.fmean(row["final_money"] for row in episode_rows),
        "max_shed_reached": sum(row["max_shed"] >= 100 for row in episode_rows),
        "aggregate_counters": dict(sorted(aggregate.items())),
        "steps_csv_check": csv_check,
    }
    (output / "episodes.json").write_text(json.dumps(episode_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(output / "episodes.csv", compact_rows)
    write_csv(output / "events.csv", event_rows)
    write_csv(output / "item_ledger.csv", ledger_rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
