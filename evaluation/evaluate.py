#!/usr/bin/env python3
"""Run paired-seed Kaggriculture evaluations and save detailed JSON/CSV."""

import argparse
import csv
import importlib.util
import json
import statistics
import time
from collections import Counter
from pathlib import Path

from kaggle_environments import make


def load_agent(path):
    spec = importlib.util.spec_from_file_location("candidate_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def classify_actions(env, candidate_index):
    counts = Counter()
    for step in env.steps[:-1]:
        state = step[candidate_index]
        action = state.action if isinstance(state.action, dict) else {}
        farmer = action.get("farmer", ["PASS"])
        counts[f"unit:{farmer[0] if farmer else 'PASS'}"] += 1
        for hand in action.get("hands", []):
            counts[f"unit:{hand[0] if hand else 'PASS'}"] += 1
        for order in action.get("market", []):
            counts[f"market:{order[0] if order else 'UNKNOWN'}"] += 1
    return dict(sorted(counts.items()))


def run_game(agent, opponent, seed, position):
    agents = [agent, opponent] if position == 0 else [opponent, agent]
    start = time.perf_counter()
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "seed": seed},
        debug=True,
    )
    env.run(agents)
    elapsed = time.perf_counter() - start
    final = env.steps[-1]
    candidate = final[position]
    other = final[1 - position]
    candidate_money = float(candidate.observation.farms[position].money)
    other_money = float(candidate.observation.farms[1 - position].money)
    status = str(candidate.status)
    if status != "DONE":
        outcome = "failure"
    elif candidate_money > other_money:
        outcome = "win"
    elif candidate_money < other_money:
        outcome = "loss"
    else:
        outcome = "draw"
    return {
        "seed": seed,
        "position": position,
        "opponent": opponent,
        "outcome": outcome,
        "status": status,
        "money": candidate_money,
        "opponent_money": other_money,
        "margin": candidate_money - other_money,
        "runtime_seconds": elapsed,
        "actions": classify_actions(env, position),
    }, env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--opponents", nargs="+", default=["pass", "random", "starter"])
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(5)))
    parser.add_argument("--output", required=True)
    parser.add_argument("--save-replay", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    agent = load_agent(args.agent)
    rows = []
    aggregate_actions = Counter()
    for opponent in args.opponents:
        for seed in args.seeds:
            for position in (0, 1):
                row, env = run_game(agent, opponent, seed, position)
                rows.append(row)
                aggregate_actions.update(row["actions"])
                print(opponent, seed, position, row["outcome"], row["money"], row["opponent_money"])
                if args.save_replay:
                    safe_opponent = "".join(
                        char if char.isalnum() or char in ("-", "_") else "_"
                        for char in opponent
                    )
                    replay = output / f"replay_{safe_opponent}_seed{seed}_p{position}.json"
                    replay.write_text(json.dumps(env.toJSON()), encoding="utf-8")

    games = len(rows)
    summary = {
        "games": games,
        "wins": sum(r["outcome"] == "win" for r in rows),
        "losses": sum(r["outcome"] == "loss" for r in rows),
        "draws": sum(r["outcome"] == "draw" for r in rows),
        "failures": sum(r["outcome"] == "failure" for r in rows),
        "win_rate": sum(r["outcome"] == "win" for r in rows) / games,
        "mean_money": statistics.fmean(r["money"] for r in rows),
        "mean_margin": statistics.fmean(r["margin"] for r in rows),
        "mean_runtime_seconds": statistics.fmean(r["runtime_seconds"] for r in rows),
        "actions": dict(sorted(aggregate_actions.items())),
        "by_opponent": {},
    }
    for opponent in args.opponents:
        subset = [r for r in rows if r["opponent"] == opponent]
        summary["by_opponent"][opponent] = {
            "games": len(subset),
            "wins": sum(r["outcome"] == "win" for r in subset),
            "losses": sum(r["outcome"] == "loss" for r in subset),
            "draws": sum(r["outcome"] == "draw" for r in subset),
            "failures": sum(r["outcome"] == "failure" for r in subset),
            "mean_money": statistics.fmean(r["money"] for r in subset),
            "mean_margin": statistics.fmean(r["margin"] for r in subset),
        }

    (output / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [k for k in rows[0] if k != "actions"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: v for k, v in row.items() if k != "actions"} for row in rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
