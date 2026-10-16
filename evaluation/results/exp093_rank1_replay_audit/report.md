# Stage A replay reconciliation report

Date: 2026-09-19  
Source: Majkel1337 submission 56156662, ten recent public replays  
Tool: `evaluation/audit_replays.py`

## Outcome

Stage A passed. The RAW archive contains ten 720-step, two-player replays. Its exported CSV contains exactly 1,440 rows per episode. All 14,400 CSV rows match the RAW replay action, observation, reward and status fields with zero mismatches.

All ten final observation money values match their replay rewards. The sum of observed per-step money changes also reconciles from the starting balance to final money in every episode. Mean final money is 120,913.7.

## Replay alignment rule

An action recorded at replay step `t` has already been applied to the observation at step `t`. Unit-action success is therefore evaluated from `observation[t-1]` to `observation[t]`, using the command stored at step `t`.

Day-boundary WATER, FEED and CARE actions can be immediately reset by the refresh at hour 0. The auditor labels these transitions `ambiguous` rather than incorrectly treating them as invalid.

## Confirmed successful investments

Across ten games:

| Item | Issued quantity | Inferred successful quantity |
|---|---:|---:|
| Cow | 93 | 93 |
| Sheep | 61 | 60 |
| Goose | 14 | 14 |
| Wheat purchases/seeds combined | 4,403 | 4,128 |
| Melon seeds | 138 | 119 |
| Strawberry seeds | 335 | 289 |
| Tomato seeds | 86 | 85 |
| Carrot seeds | 262 | 262 |

The difference between issued and successful quantities confirms that the replay contains speculative or unaffordable orders. Issued commands must not be interpreted as completed purchases.

The agent issued 34 BUY_LAND orders, but exactly 20 succeeded: NE at step 150/day 6 and SW at steps 218-228/day 9 in every game. It issued 2,918 HIRE orders and 2,862 succeeded. All issued sale quantities reconciled exactly with available shed inventory.

## Unit-action results

Confirmed successful actions include:

- 3,437 FEED;
- 3,447 CARE;
- 3,733 fertilizer collections;
- 1,507 FERTILIZE;
- 4,683 HARVEST;
- 2,666 PLANT;
- 11,898 WATER, plus 850 day-boundary ambiguous water actions.

No-effect counts include collisions, duplicate actors targeting the same tile, movement blocked by the board, missing inventory and commands obscured by state changes. They are retained in `events.csv` for per-step inspection rather than automatically classified as agent bugs.

## Animal removal

The board transitions confirm 35 sheep and 6 cows disappeared. Structures containing animals cannot be dug, so these removals are animal escapes. Their timing matches the previously observed endgame service shutdown. This is successful confirmation of deliberate or accepted culling rather than a count inferred only from peak versus final herd.

## Inventory loss

The earlier hypothesis that shed overflow was large is rejected.

- Confirmed DROP overflow: one strawberry across all ten games.
- Inventory carried by hands when daily employment expired: 259 items.
  - wheat 113;
  - fertilizer 50;
  - strawberry 45;
  - melon 19;
  - carrot 14;
  - milk 9;
  - tomato 5;
  - wool 4.
- Remaining unexplained residual: 7 fertilizer and 1 wheat.

The eight unexplained units are immaterial relative to total throughput but remain explicitly visible. Likely causes are hour-0 refresh ambiguity and simultaneous same-tile actions. They are not silently assigned to overflow.

This reveals a transferable improvement over the rank 1 behavior: force hired hands to DROP before the last turn of each day. Preventing hand-expiry loss could recover roughly 26 items per game without changing the economic strategy.

## Generated outputs

- `summary.json`: aggregate checks and counters;
- `episodes.json`: full per-episode summaries;
- `episodes.csv`: compact episode table;
- `events.csv`: issued unit and market actions with inferred outcomes;
- `item_ledger.csv`: step-level private inventory reconciliation.

The CLI accepts replay JSON files, directories, globs or RAW zip archives. A player can be selected by `--team` or `--player`. An optional `--steps-csv` performs the CSV-versus-RAW consistency check.

## Stage B implications

The Stage B opening should use inferred successful quantities, not raw issued orders. In particular:

- two cows and three sheep are reliably purchased on day 0;
- successful melon stock/planting converges to roughly 12 rather than the 13-17 issued quantities;
- strawberry orders deliberately over-request and achieve 14-39 successful purchases depending on the game;
- the reconstruction should not copy repeated failed BUY_LAND or seed orders as intentional investment volume;
- end-of-day hand evacuation should be added as an explicit reliability improvement.

No strategy agent or Kaggle submission was changed.
