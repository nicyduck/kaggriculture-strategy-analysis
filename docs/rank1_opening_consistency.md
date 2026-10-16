# Rank 1 opening consistency and first divergence

## Scope

This check uses the ten public replays captured on 2026-09-13 for Majkel1337's
submission `56156662`. The capture contained 720 steps for two players in every
episode. The accompanying step export was reconciled against the RAW replay in
`exp093`; all 14,400 player-step rows matched.

The comparison selects Majkel1337's player index in each episode, normalizes the
JSON action object, and compares the full farmer, hired-hand, and market command
at every step.

## Result

The action policy is exactly identical for steps `0` through `22` in all ten
replays. In other words, the first 23 recorded steps form a deterministic
opening. The first divergence occurs at step `23`.

At step 23, all games issue `WATER` for the farmer and first hand. The remaining
actions split into two variants:

| Variant | Episodes | Full hand tail |
|---|---:|---|
| A | 6 | `PLANT WHEAT`, `PLANT WHEAT`, `PASS` |
| B | 4 | `PLANT WHEAT`, `PASS`, `PASS` |

The difference is therefore not an early strategic branch. It is a one-tile
wheat completion difference caused by the realized state after an otherwise
fixed opening. Step 24 preserves the same 6/4 split in watering work. Step 25
converges again before later paths diverge more substantially.

## What the fixed opening does

Across all ten games, the common prefix:

1. buys one cow and five wheat, then buys another cow and three sheep;
2. hires four hands on day 0;
3. places and services a two-cow, three-sheep starting herd;
4. plants twelve melons and a block of wheat;
5. repeatedly sells or buys single wheat units to keep the low-cash opening
   feasible.

The state-transition audit is important here: an issued command is not assumed
to have succeeded. Later analysis uses observed inventory, money, and board
changes rather than treating speculative market orders as completed purchases.

## Reproduce

After obtaining the two private capture files, run:

```bash
python evaluation/analyze_opening_consistency.py \
  --steps-csv /path/to/kaggriculture_rank1_steps.csv \
  --episodes evaluation/results/exp093_rank1_replay_audit/episodes.csv \
  --through-step 30
```

The command prints the common prefix length and a compact per-step variant
table. Raw replays and the step export are excluded from this repository because
they are large captured competition artifacts.

