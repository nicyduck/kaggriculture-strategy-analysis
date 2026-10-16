# Rank 1 strategy reconstruction plan

Date: 2026-09-19  
Reference: Majkel1337 submission 56156662, ten public replays captured 2026-09-13  
Current baseline: v12 dynamic 12-14 livestock

This document defines the design, decision formulas, and staged local experiments to reproduce the observed rank 1 behavior. It does not change an agent or submit to Kaggle.

## 1. Objective and constraints

The objective is to reproduce the transferable policy behind the rank 1 agent rather than copy one observed board layout. The target policy must:

- buy NE near day 6 and SW near day 9;
- support about 50-60 crop tiles and 14-23 animals on three quadrants;
- adapt the livestock mix to shops, prices, opponent production and remaining days;
- use fertilizer as a production input, especially on strawberry and wheat;
- rotate crops as the remaining season shortens;
- stop maintaining an animal when its remaining value is negative;
- preserve market-order capacity and avoid shed overflow;
- remain testable through one-feature-at-a-time experiments.

The ten rank 1 replays are observational evidence. Exact hidden constants are unknown. Every threshold below is therefore an initial hypothesis that must be calibrated locally.

## 2. Baseline gap

| Component | v12 | Rank 1 observation | Reconstruction target |
|---|---|---|---|
| Opening herd | 3 cows, 2 sheep | 2 cows, 3 sheep | reproduce 2/3 opening in an isolated test |
| Opening cash | retains operating flexibility | approximately 0 by day 1 | permit near-zero cash only for fixed opening bundle |
| Land | money/profit gates | NE day 6, SW day 9 | scheduled purchase with safety fallback |
| Daily hands | workload-derived, generally lower | 11 from day 10-27 | explicit capacity schedule, later workload refinement |
| Peak crops | about 43 | mean 56.6 | at least 52 without neglect deaths |
| Peak animals | 12-14 | mean 16.7, range 14-23 | greedy marginal selection up to 23 |
| Crop mix | score-based, often wheat-heavy | 12 melon, strawberry wave, late wheat/short crops | phase-based portfolio with demand overlay |
| Fertilizer | mainly collected/sold | about 152 applications per game | reserve and apply by marginal yield value |
| Endgame herd | survival invariant through day 28 | product-specific culling from day 24 | remaining-production-value rule |
| Sales | sell all shed goods | frequent small batches; shed repeatedly reaches 100 | capacity-aware small-batch liquidation |

## 3. Agent architecture

The reconstruction should be a new agent directory. It should not overwrite v12. The design has six independent policy modules sharing one state summary.

### 3.1 State summary

At every turn calculate:

- current and remaining day/turn;
- own and opponent crop counts by product;
- own and opponent animals by type and placement day;
- visible shop multiplicity;
- current market inventory and price by product;
- own shed, carried inventory and seed stock;
- unlocked land and occupied cells;
- daily outstanding actions: feed, care, harvest, fertilizer collection, water, crop harvest, planting and delivery;
- market-order slots remaining;
- projected town demand until the next production/sale window.

All investment and culling functions consume this same summary. Board routing must not contain separate economic decisions.

### 3.2 Phase controller

Use explicit phases so the crop and investment rules remain interpretable.

| Phase | Days | Main objective |
|---|---:|---|
| Opening | 0-5 | establish 2 cows, 3 sheep, 12 melons, wheat and early strawberries |
| NE expansion | 6-8 | buy NE, choose first shop-conditioned livestock block, plant strawberry/wheat |
| SW expansion | 9-13 | buy SW, reach mature workforce, complete adaptive herd and fill crop cells |
| Production | 14-22 | maintain full utilization, harvest recurring products, replant by forecast value |
| Short-cycle | 23-27 | prefer wheat/carrot and only crops that finish with delivery slack |
| Liquidation | 28-29 | stop new planting, cull negative-value animals, harvest/drop/sell all remaining goods |

### 3.3 Fixed opening hypothesis

Initial version:

- day 0 purchases: 2 cows, 3 sheep, 19 wheat seeds, 6 melon seeds and four hires, subject to the 10-order limit;
- plant toward 12 successful melon tiles over days 0-2 and 11-12 initial wheat tiles;
- start two strawberry tiles on day 2, then expand the strawberry wave on days 3-7;
- allow operating cash to approach zero after the opening order, but never issue a later purchase that prevents next-day feed.

The exact day-0 order must be validated against simultaneous market processing. Issued commands in replay are not proof that every command succeeded.

### 3.4 Land and workforce schedule

Land targets:

- buy NE at day 6, earliest feasible turn, with a fallback deadline of day 7;
- buy SW at day 9, earliest feasible turn, with a fallback deadline of day 10;
- do not buy SE in the first reconstruction series.

Initial hand schedule, excluding the main farmer:

| Day | Hands |
|---:|---:|
| 0 | 4 |
| 1 | 9-10 |
| 2-5 | 6 |
| 6 | 8 |
| 7-9 | 9 |
| 10-27 | 11 |
| 28-29 | 10 |

After schedule reproduction is stable, replace it with a workload floor plus cap:

```text
required_actions =
    1.0 * animals_not_fed
  + 1.0 * animals_with_product
  + care_weight * animals_not_cared
  + fertilizer_collect_weight * animals_with_fertilizer
  + 1.0 * plants_not_watered
  + 1.0 * harvestable_plants
  + setup_and_delivery_actions
  + estimated_travel_actions

hands = clamp(ceil(required_actions / 24) - 1, schedule_floor[day], 11)
```

Initial weights: `care_weight=1.0`, `fertilizer_collect_weight=0.7`. Travel actions should be measured from replay traces, not guessed permanently.

## 4. Livestock decision formulas

### 4.1 Shop demand per day

Town center consumes one unit per product per day. A normal shop consumes one unit every four turns, or six units per day. A single-product shop consumes twice that amount.

```text
daily_demand(EGG)  = 1 + 6 * (Bakery + Brunch Spot)
daily_demand(MILK) = 1 + 6 * (Pizza Shop + Ice Cream Shop + Smoothie Shop)
daily_demand(WOOL) = 1 + 12 * Yarn Store
```

Duplicate shops count independently.

### 4.2 Future market inventory

For product `p` and horizon `h` days:

```text
future_inventory[p,h] =
    current_market_inventory[p]
  + expected_own_supply[p,h]
  + expected_opponent_supply[p,h]
  - daily_demand[p] * h
  - remaining_town_ticks_within_h[p]
```

Opponent supply uses visible animal type, placement day and production interval. Use a conservative care multiplier until the opponent's realized yield pattern is observed.

Convert future inventory to price with the official market curve. Evaluate price before each scheduled production sale rather than using only the current price.

### 4.3 Expected animal output

For an animal placed on day `d`, enumerate every production day through day 29:

```text
first production: goose d+4, sheep d+6, cow d+8
interval: goose 1, cow 2, sheep 3 days
base output: 1
care output: add the accumulated fed-and-cared bonus, capped by max held
```

For the first model, assume daily care and prompt harvesting. Verify the predicted output against local traces and then reduce it by the observed service rate.

### 4.4 Marginal animal value

For candidate animal `a`:

```text
animal_value[a] =
    sum_over_future_productions(
        expected_units[a,t] * predicted_marginal_sale_price[product(a),t]
    )
  + expected_fertilizer_units[a] * predicted_fertilizer_price
  - animal_purchase_cost[a]
  - expected_feed_units[a] * predicted_wheat_replacement_cost
  - tile_opportunity_cost[a]
  - labor_opportunity_cost[a]
  - overflow_risk_cost[a]
```

Definitions:

- `predicted_marginal_sale_price` applies the price function after adding the candidate's supply;
- `wheat_replacement_cost` is the higher of expected wheat seed/production opportunity cost and expected market buy price;
- `tile_opportunity_cost` is the best crop profit available on that cell over the same remaining horizon;
- `labor_opportunity_cost` is the value of displaced crop/harvest actions plus the marginal Fibonacci hire cost;
- `overflow_risk_cost` becomes large when projected shed occupancy exceeds 90 without sufficient market slots.

Buy the best candidate while all conditions hold:

```text
animal_value[best] >= investment_margin
projected_daily_actions <= 24 * (1 + planned_hands) * utilization_limit
projected_feed_reserve >= 2 * projected_animals
total_animals < 23
```

Initial constants:

- `investment_margin = 300` before day 10, 600 on days 10-13, 1,000 after day 13;
- `utilization_limit = 0.82`, leaving travel and recovery capacity;
- no purchases after day 18;
- keep at least two days of wheat after the purchase.

### 4.5 First shop-conditioned branch

Before the full marginal model is calibrated, use this interpretable rule:

```text
if day <= 6 and Yarn Store count >= 1 and projected wool price stays above 120:
    target sheep = 17
    target cows = 5 to 6
    target geese = 0
else:
    target sheep = 3
    choose cows and geese greedily by animal_value
    normal total target = 14 to 17
```

The `120` wool threshold is deliberately conservative and must be swept. The observed sheep-heavy games realized average wool prices of 182 and 242, but ten replays do not identify the true cutoff.

### 4.6 Endgame culling

For every animal at the start of each day from day 23 onward:

```text
remaining_value =
    value_of_remaining_productions
  + value_of_collectable_fertilizer
  - remaining_feed_cost
  - remaining_care_feed_harvest_travel_cost

service animal only if remaining_value > 0
```

Also stop CARE after the last production that can occur before the final sell deadline. Stop FEED when no profitable scheduled production remains. Natural escape is acceptable because animals have no terminal value.

The culling decision must be product-specific. Do not stop all feeding merely because the calendar reaches a fixed day.

## 5. Crop decision formulas

### 5.1 Initial phase targets

- Melon: target 12 successful occupied cells by day 2.
- Strawberry: begin on day 2 and fill most new premium-crop capacity through day 7; initial target 24-30 cells, modified by demand and opponent supply.
- Wheat: maintain at least `2 * animals + next_two_days_feed` accessible units across shed, inventories and harvest schedule.
- Tomato/carrot: introduce from midgame when their demand-adjusted value exceeds replacement wheat.

### 5.2 Crop value

```text
crop_value_per_tile[c] =
    sum(expected_yield[c,t] * predicted_price[c,t])
  - seed_cost[c]
  - water_action_cost[c]
  - harvest_action_cost[c]
  - fertilizer_cost[c]
  - delivery_cost[c]
```

The crop is viable only if its final harvest can be deposited and sold before step 719. Use predicted future inventory, including opponent crops and shop demand.

Phase bonuses for the initial reconstruction:

- days 0-2: force melon/wheat targets before free selection;
- days 2-7: multiply strawberry value by 1.20 until its target is filled;
- days 8-22: no phase bonus; use projected value;
- days 23-27: multiply wheat by 1.25 and reject any crop without two delivery turns of slack;
- days 28-29: no planting.

### 5.3 Fertilizer allocation

Apply fertilizer only when its incremental revenue exceeds its alternative sale value plus the worker action cost:

```text
fertilize_gain[crop] =
    additional_expected_units * predicted_crop_price
  - predicted_fertilizer_sale_price
  - action_and_travel_cost
```

Prioritize the highest positive gain. Expected first priority is strawberry during its bonus windows, then feed/sale wheat. Do not fertilize crops already at their yield cap.

## 6. Sales and storage policy

Use two thresholds per product:

- `reserve_price[p,day]`: hold while a better near-term price is likely;
- `forced_sale_inventory[p]`: sell regardless of price when shed pressure is high.

```text
sell now if
    current_price >= reserve_price[p,day]
    or shed_total >= 85
    or product_inventory >= forced_sale_inventory[p]
    or remaining_sale_windows <= liquidation_threshold
```

Initial order-size targets, based on observed medians:

- fertilizer 1-2;
- milk/wool/egg 2-4;
- strawberry/tomato 2-4;
- wheat 6-8;
- melon 6.

Batch size may expand when shed occupancy exceeds 90. Reserve at least one market slot for urgent feed or investment before day 18. On day 29, market sales and DROP routing take absolute priority.

## 7. Staged experiment plan

Every stage uses the previous accepted stage as its base. Rejecting a stage returns to the last accepted version. Do not combine two untested strategic changes.

### Stage A: forensic replay checks

Purpose: validate the extracted rules before coding.

- Recalculate successful purchases rather than issued orders.
- Reconstruct daily animal counts, successful placements and actual escape causes.
- Reconcile crop harvest quantities with sales and final inventory.
- Measure travel actions and shed-overflow losses.
- Verify that early Yarn Store is observable before the sheep purchase decision.

Pass condition: all ten episodes reconcile final money and herd/crop transitions without unexplained material inventory loss.

### Stage B: opening bundle only

Change: reproduce 2 cows, 3 sheep, 12 melons, early wheat and four day-0 hands. Keep v12 land, later herd and crop logic.

Test: seeds 0-19, both player positions, versus v5, v7, v12, starter and random.

Pass conditions:

- zero animal escapes before day 23;
- no more than two premature crop deaths per game after setup stabilization;
- mean day-10 money no worse than v12 by more than 1,000;
- mean final money improves or remains within 2% while setup reliability improves.

### Stage C: fixed day-6/day-9 land and workforce schedule

Change: add the land and hand schedule; no new animal/crop adaptation.

Pass conditions:

- NE bought by day 7 in at least 95% of games and SW by day 10 in at least 90%;
- peak crops at least 50 in 80% of games;
- overdue watering/feeding never reaches two consecutive days before deliberate culling;
- mean own money increases at least 8% over Stage B;
- runtime remains below Kaggle timeout with p99 reported.

### Stage D: crop lifecycle and fertilizer

Change: add melon target, strawberry wave, late short-crop rotation and fertilizer allocation.

Parameter sweep:

- strawberry target: 20, 24, 28, 32;
- fertilizer gain margin: 0, 25, 50;
- late wheat bonus: 1.0, 1.25, 1.5.

Pass conditions:

- mean crop gross revenue at least 45,000 initially, then target 60,000;
- mean final money improves at least 10% over Stage C;
- no increase in animal escape or shed loss;
- performance remains positive against both livestock-heavy and crop-heavy opponents.

### Stage E: shop-conditioned livestock

Change: add early Yarn branch and greedy marginal animal selection.

Scenario matrix:

- 0, 1, 2 and 4 Yarn Stores;
- milk-demand shops 0, 2, 4 and 6;
- opponent herds: none, cow-heavy, sheep-heavy, goose-heavy and mixed;
- total herd caps: 17, 20 and 23;
- wool threshold sweep: 80, 120, 160 and model-only without a hard threshold.

Pass conditions:

- selected herd changes in the intended direction across scenarios;
- sheep-heavy branch beats the normal branch when Yarn demand is high;
- normal branch wins under no-Yarn controls;
- no configuration is selected if projected action utilization exceeds 82%;
- aggregate mean money improves at least 5% over Stage D without worsening the 20th-percentile score.

### Stage F: endgame culling and liquidation

Change: add remaining-value service decisions from day 23 and capacity-aware sales.

Pass conditions:

- every deliberately abandoned animal has non-positive predicted remaining value at the decision turn;
- saved feed and labor value exceeds lost product value on replay audit;
- final unsold shed/carried value is below 1% of final money;
- mean day-23-to-final money growth improves over Stage E;
- no premature culling before the last profitable production.

### Stage G: full validation

Test at least:

- 50 seeds x both positions versus v7 and v12;
- 30 seeds x both positions versus livestock-heavy, crop-heavy and shop-demand scenario agents;
- pass, random and starter only as mechanical controls;
- replay traces for the worst five scores, worst five margins and all escapes/overflows.

Selection criteria:

1. primary: mean final money;
2. secondary: 20th-percentile final money and median margin;
3. constraints: no unintended consecutive feed/water misses, no unexplained overflow, no runtime failure;
4. accept only if improvement is visible across opponent classes, not solely against v5.

## 8. Required instrumentation

Each evaluation summary should record:

- final money, opponent money and margin;
- money by day;
- actual land purchase steps;
- daily hand count and hire cost;
- animal purchases, placements, production and culling decisions;
- crop occupied cells by type and day;
- water/feed/care misses;
- fertilizer collected, used and sold;
- market wheat bought, own wheat harvested, wheat sold and wheat fed;
- sales quantity and realized price by product;
- predicted versus actual future inventory and price at every investment decision;
- shed occupancy, overflow and unsold terminal value;
- issued invalid/no-op commands and runtime percentiles.

## 9. Implementation order

1. Build the replay reconciliation/instrumentation layer.
2. Create a new reconstruction agent copied only as a mechanical routing baseline, with economic modules separated.
3. Implement Stage B and validate.
4. Continue one accepted stage at a time through Stage F.
5. Run Stage G before considering any Kaggle submission.

No Kaggle submission should occur automatically. The latest-two-submission constraint must be checked immediately before any future submission.
