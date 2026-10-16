# Reproduction guide

## Environment

The analysis scripts use Python 3.11+ and the standard library. Local match
evaluation additionally requires the Kaggriculture environment supplied by the
competition.

## Audit a replay capture

Given a RAW replay archive and its optional exported steps CSV:

```bash
python evaluation/audit_replays.py \
  /path/to/kaggriculture_rank1_RAW.zip \
  --team Majkel1337 \
  --steps-csv /path/to/kaggriculture_rank1_steps.csv \
  --output evaluation/results/replay_audit
```

The auditor checks CSV/RAW agreement, infers whether actions changed the state,
reconciles money and inventory, and writes episode/event ledgers. The step
alignment rule is `observation[t-1] -> observation[t]` for the command stored at
step `t`.

## Extract the strategy summary

```bash
python evaluation/extract_rank1_strategy.py \
  /path/to/kaggriculture_rank1_RAW.zip \
  --team Majkel1337 \
  --output evaluation/results/rank1_strategy
```

## Check the deterministic opening

```bash
python evaluation/analyze_opening_consistency.py \
  --steps-csv /path/to/kaggriculture_rank1_steps.csv \
  --episodes evaluation/results/exp093_rank1_replay_audit/episodes.csv
```

## Repository policy

Official competition files, raw replays, generated match logs, trained bundles,
and submission archives are intentionally ignored. They are either governed by
Kaggle's competition rules or are too large for source control. The repository
keeps the authored agents, evaluation code, experiment registry, compact
summaries, and human-readable conclusions needed to understand and repeat the
work.

