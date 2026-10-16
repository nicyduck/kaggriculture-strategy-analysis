"""Compare a selected player's opening actions across captured replay rows."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find the exact common action prefix across replay episodes."
    )
    parser.add_argument("--steps-csv", required=True, type=Path)
    parser.add_argument(
        "--episodes",
        required=True,
        type=Path,
        help="episodes.csv emitted by audit_replays.py; supplies player index",
    )
    parser.add_argument("--through-step", type=int, default=30)
    return parser.parse_args()


def canonical_action(raw: str) -> str:
    return json.dumps(
        json.loads(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def load_players(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["episode_id"]: row["player"]
            for row in csv.DictReader(handle)
        }


def main() -> None:
    args = parse_args()
    players = load_players(args.episodes)
    actions: dict[str, dict[int, str]] = defaultdict(dict)

    with args.steps_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            episode_id = row["episode_id"]
            step = int(row["step"])
            if (
                episode_id in players
                and row["player"] == players[episode_id]
                and step <= args.through_step
            ):
                actions[episode_id][step] = canonical_action(row["action_json"])

    episode_ids = sorted(actions, key=int)
    if not episode_ids:
        raise SystemExit("No selected-player rows were found.")

    common_prefix = 0
    rows: list[tuple[int, Counter[str]]] = []
    for step in range(args.through_step + 1):
        variants = Counter(actions[episode].get(step, "<missing>") for episode in episode_ids)
        rows.append((step, variants))
        if len(variants) == 1 and step == common_prefix:
            common_prefix += 1

    print(f"episodes={len(episode_ids)}")
    print(f"common_prefix_steps={common_prefix} (steps 0..{common_prefix - 1})")
    for step, variants in rows:
        counts = ", ".join(str(count) for count in sorted(variants.values(), reverse=True))
        label = "same" if len(variants) == 1 else "DIFF"
        print(f"step={step:>3} {label:<4} variants={len(variants)} counts=[{counts}]")


if __name__ == "__main__":
    main()

