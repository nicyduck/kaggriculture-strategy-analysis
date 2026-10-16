"""Full-utilization strategy with capacity staffing per unlocked quadrant.

It concentrates early cash into recurring livestock production, sizes the daily
workforce from estimated workload, sweeps from the shed toward the field edge,
and stops investments near season end. It may unlock NE and replicate the unit.
"""

PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
SHED_TILES = {(4, 4), (5, 4), (4, 5), (5, 5)}
NW_ANIMAL_CELLS = [(4, 4), (3, 4), (4, 3), (2, 4), (3, 3)]
NE_ANIMAL_CELLS = [(5, 4), (6, 4), (5, 3), (7, 4), (6, 3)]
GOOSE_CELLS = [(4, 5)]
OPTIONAL_ANIMAL_CELLS = [(2, 5), (4, 7)]
SW_ANIMAL_CELLS = [(3, 5), (4, 6)] + OPTIONAL_ANIMAL_CELLS
ANIMAL_CELLS = NW_ANIMAL_CELLS + NE_ANIMAL_CELLS + GOOSE_CELLS + SW_ANIMAL_CELLS
DESIRED_ANIMAL = {
    (4, 4): "COW", (3, 4): "COW", (4, 3): "COW",
    (2, 4): "SHEEP", (3, 3): "SHEEP",
    (5, 4): "COW", (6, 4): "COW", (5, 3): "COW",
    (7, 4): "SHEEP", (6, 3): "SHEEP",
    (4, 5): "GOOSE",
    (3, 5): "COW", (2, 5): "COW", (4, 6): "SHEEP", (4, 7): "SHEEP",
}
NW_CROP_CELLS = [
    (x, y)
    for y in range(5)
    for x in range(5)
    if (x, y) not in NW_ANIMAL_CELLS
]
NE_CROP_CELLS = [
    (x, y)
    for y in range(5)
    for x in range(5, 10)
    if (x, y) not in NE_ANIMAL_CELLS
]
SW_CROP_CELLS = [
    (x, y) for y in range(5, 10) for x in range(5)
    # Optional livestock slots remain productive crop cells unless the live
    # opponent/market calculation commits an extra animal to them.
    if (x, y) not in SW_ANIMAL_CELLS or (x, y) in OPTIONAL_ANIMAL_CELLS
]
SE_CROP_CELLS = [(x, y) for y in range(5, 10) for x in range(5, 10)]
CROP_CELLS = NW_CROP_CELLS + NE_CROP_CELLS + SW_CROP_CELLS + SE_CROP_CELLS
CROP_GROUPS = (NW_CROP_CELLS, NE_CROP_CELLS, SW_CROP_CELLS, SE_CROP_CELLS)


def _count(inv, item):
    return int(inv.get(item, 0)) if isinstance(inv, dict) else 0


def _move_toward(pos, target):
    """Deterministic Manhattan routing; all v0 targets lie in unlocked NW."""
    x, y = pos
    tx, ty = target
    if x < tx:
        return ["EAST"]
    if x > tx:
        return ["WEST"]
    if y < ty:
        return ["SOUTH"]
    if y > ty:
        return ["NORTH"]
    return ["PASS"]


def _nearest(pos, candidates):
    return min(
        candidates,
        key=lambda p: (abs(pos[0] - p[0]) + abs(pos[1] - p[1]), p[1], p[0]),
    )


def _tile(board, pos):
    x, y = pos
    return board[y][x]


def _strawberry_viable(prices):
    """Current gross profit must exceed half the base gross profit (380)."""
    price = float(prices.get("STRAWBERRY", 120))
    return 4 * price - 100 > 190


def _crop_can_finish(crop, day):
    remaining = 29 - day
    return remaining >= {
        "WHEAT": 2, "CARROT": 2, "TOMATO": 8,
        "STRAWBERRY": 10, "MELON": 10,
    }[crop]


def _crop_scores(day, prices, own_counts, opponent_counts, prefer_wheat):
    """Expected profit/day adjusted for our saturation and opponent supply."""
    economics = {
        "WHEAT": (4, 10, 4, 25),
        "CARROT": (3, 20, 3, 35),
        "TOMATO": (4, 50, 12, 60),
        "STRAWBERRY": (4, 100, 17, 120),
        "MELON": (6, 80, 10, 250),
    }
    scores = {}
    pressure_rate = {
        "WHEAT": 0.02, "CARROT": 0.04, "TOMATO": 0.07,
        "STRAWBERRY": 0.12, "MELON": 0.15,
    }
    soft_share_cap = {
        "WHEAT": 1.00, "CARROT": 0.30, "TOMATO": 0.20,
        "STRAWBERRY": 0.20, "MELON": 0.15,
    }
    total_own = max(1, sum(own_counts.values()))
    for crop, (units, seed_cost, occupied_days, base_price) in economics.items():
        if not _crop_can_finish(crop, day):
            continue
        price = float(prices.get(crop, base_price))
        daily_net = max(0.0, units * price - seed_cost) / occupied_days
        rate = pressure_rate[crop]
        own_pressure = 1.0 + rate * own_counts.get(crop, 0)
        opponent_pressure = 1.0 + 1.5 * rate * opponent_counts.get(crop, 0)
        scarcity_bonus = 1.20 if opponent_counts.get(crop, 0) == 0 else 1.0
        share_penalty = (
            0.25 if own_counts.get(crop, 0) / total_own >= soft_share_cap[crop] else 1.0
        )
        scores[crop] = daily_net * scarcity_bonus * share_penalty / (own_pressure * opponent_pressure)
    if prefer_wheat and "WHEAT" in scores:
        scores["WHEAT"] *= 4.0
    return scores


def _preferred_crop(day, prices, prefer_wheat, own_counts, opponent_counts):
    if day < 5:
        return "WHEAT"
    scores = _crop_scores(day, prices, own_counts, opponent_counts, prefer_wheat)
    return max(scores, key=scores.get) if scores else "WHEAT"


def _animal_marginal_score(animal, day, prices, opponent_count, crop_daily_net):
    """Conservative value of one optional animal placed roughly tomorrow."""
    data = {
        "COW": (400, "MILK", 8, 2, 6, 3),
        "SHEEP": (500, "WOOL", 6, 3, 6, 4),
    }
    cost, product, first, interval, first_units, later_units = data[animal]
    placed_day = day + 1
    first_product_day = placed_day + first
    if first_product_day > 29:
        return -1e9
    productions = (29 - first_product_day) // interval + 1
    units = first_units + max(0, productions - 1) * later_units
    gross = units * float(prices.get(product, 1))
    # Current price captures realized supply; visible opponent animals predict
    # additional supply that has not reached the market yet.
    future_supply_discount = 1.20 if opponent_count == 0 else max(0.65, 1.0 - 0.05 * opponent_count)
    feed_days = max(0, 29 - placed_day)
    feed_cost = feed_days * float(prices.get("WHEAT", 25))
    crop_opportunity = crop_daily_net * max(0, 29 - placed_day)
    labor_allowance = 18 * max(0, 29 - placed_day)
    return gross * future_supply_discount - cost - feed_cost - crop_opportunity - labor_allowance


def _home_distance(pos):
    """Distance from the shed corner belonging to the cell's quadrant."""
    x, y = pos
    access = (4 if x < 5 else 5, 4 if y < 5 else 5)
    return abs(x - access[0]) + abs(y - access[1])


def _all_unlocked_quadrants_full(board):
    """Treat 80% occupancy as proof that the quadrant can be kept filled."""
    for x0 in (0, 5):
        cells = [board[y][x] for y in range(5) for x in range(x0, x0 + 5)]
        if all(cell == "LOCKED" for cell in cells):
            continue
        occupied = sum(cell is not None and cell != "LOCKED" for cell in cells)
        if occupied < 20:
            return False
    return True


def _quadrant_occupancy(board, pos):
    x0 = 0 if pos[0] < 5 else 5
    y0 = 0 if pos[1] < 5 else 5
    return sum(
        board[y][x] is not None and board[y][x] != "LOCKED"
        for y in range(y0, y0 + 5) for x in range(x0, x0 + 5)
    )


def _plant_count(board, cells):
    return sum(
        isinstance(_tile(board, p), dict) and _tile(board, p).get("kind") == "PLANT"
        for p in cells
    )


def _lane_chunk(cells, lane, lanes=3):
    """Return a geographically contiguous column band, shed side first."""
    if not cells:
        return []
    xs = sorted(
        {p[0] for p in cells},
        key=lambda x: (abs(x - (4 if x < 5 else 5)), x),
    )
    width = (len(xs) + lanes - 1) // lanes
    lane_xs = set(xs[lane * width:(lane + 1) * width])
    return sorted(
        (p for p in cells if p[0] in lane_xs),
        key=lambda p: (_home_distance(p), p[1], p[0]),
    )


def _crop_land_is_profitable(day, prices, land_cost, money):
    """Buy only when conservative wheat payback beats land and operating cash."""
    remaining_days = max(0, 29 - day)
    wheat_cycles = remaining_days // 4
    net_per_tile = wheat_cycles * max(0.0, 4 * float(prices.get("WHEAT", 25)) - 10)
    projected_net = 25 * net_per_tile
    seed_budget = 25 * 10
    operating_reserve = 1500
    return (
        wheat_cycles >= 2
        and projected_net >= 1.35 * (land_cost + seed_budget)
        and money >= land_cost + seed_budget + operating_reserve
    )


def _owned_count(board, shed, inventories, animal):
    placed = sum(
        isinstance(_tile(board, p), dict) and _tile(board, p).get("animal") == animal
        for p in ANIMAL_CELLS
    )
    carried = sum(_count(inv, animal) for inv in inventories)
    return placed + _count(shed, animal) + carried


def _urgent_feed_action(pos, inv, board, shed, reserved, day):
    """Make feeding a farm-wide priority before role-specific work."""
    if day > 28:
        return None
    here = _tile(board, pos)
    if (
        isinstance(here, dict)
        and here.get("animal")
        and not here.get("fed_today", False)
        and _count(inv, "WHEAT") > 0
    ):
        return ["FEED"]
    candidates = [
        p for p in ANIMAL_CELLS
        if p not in reserved
        and isinstance(_tile(board, p), dict)
        and _tile(board, p).get("animal")
        and not _tile(board, p).get("fed_today", False)
    ]
    if not candidates:
        return None
    if _count(inv, "WHEAT") == 0:
        if _count(shed, "WHEAT") <= 0:
            return None
        if pos in SHED_TILES:
            return ["PICKUP", "WHEAT", min(4, _count(shed, "WHEAT"))]
        return _move_toward(pos, _nearest(pos, list(SHED_TILES)))
    target = _nearest(pos, candidates)
    reserved.add(target)
    return ["FEED"] if pos == target else _move_toward(pos, target)


def _animal_action(pos, inv, board, shed, reserved, day):
    """Return an animal-oriented action and reserve its selected target."""
    here = _tile(board, pos)

    # Optional livestock slots are ordinary crop land until a dynamically
    # selected animal has actually been purchased. Reclaim only that exact slot.
    optional_reclaims = [
        p for p in OPTIONAL_ANIMAL_CELLS
        if p not in reserved
        and isinstance(_tile(board, p), dict)
        and _tile(board, p).get("kind") == "PLANT"
        and (_count(shed, DESIRED_ANIMAL[p]) > 0 or _count(inv, DESIRED_ANIMAL[p]) > 0)
    ]
    if optional_reclaims:
        target = _nearest(pos, optional_reclaims)
        reserved.add(target)
        return ["DIG"] if pos == target else _move_toward(pos, target)

    # Once standing on an animal, finish its daily safety-critical work first.
    if isinstance(here, dict) and here.get("animal"):
        if day <= 28 and not here.get("fed_today", False) and _count(inv, "WHEAT") > 0:
            return ["FEED"]
        if here.get("yield_units", 0) > 0:
            return ["HARVEST"]
        if day <= 28 and not here.get("cared_today", False):
            return ["CARE"]
        if day <= 28 and here.get("fertilizer_available", False):
            return ["COLLECT_FERTILIZER"]

    # Empty structures need their designated animal carried from the shed.
    empty_structures = [
        p for p in ANIMAL_CELLS
        if p not in reserved
        and isinstance(_tile(board, p), dict)
        and _tile(board, p).get("kind")
        == ("COOP" if DESIRED_ANIMAL[p] == "GOOSE" else "PASTURE")
        and not _tile(board, p).get("animal")
    ]
    for animal in ("COW", "SHEEP", "GOOSE"):
        candidates = [p for p in empty_structures if DESIRED_ANIMAL[p] == animal]
        if candidates and _count(inv, animal) > 0:
            target = _nearest(pos, candidates)
            reserved.add(target)
            return ["PLACE", animal] if pos == target else _move_toward(pos, target)
        if candidates and _count(shed, animal) > 0 and _count(inv, animal) == 0:
            if tuple(pos) in SHED_TILES:
                return ["PICKUP", animal, 1]
            return _move_toward(pos, _nearest(pos, list(SHED_TILES)))

    # Build the small, shed-adjacent livestock block.
    build_cells = [
        p for p in ANIMAL_CELLS
        if p not in reserved
        and _tile(board, p) is None
        and (
            (p not in OPTIONAL_ANIMAL_CELLS and DESIRED_ANIMAL[p] != "GOOSE")
            or (
                (p in OPTIONAL_ANIMAL_CELLS or DESIRED_ANIMAL[p] == "GOOSE")
                and (
                    _count(shed, DESIRED_ANIMAL[p]) > 0
                    or _count(inv, DESIRED_ANIMAL[p]) > 0
                )
            )
        )
    ]
    if build_cells:
        target = _nearest(pos, build_cells)
        reserved.add(target)
        build_op = "BUILD_COOP" if DESIRED_ANIMAL[target] == "GOOSE" else "BUILD_PASTURE"
        return [build_op] if pos == target else _move_toward(pos, target)

    animals = [
        p for p in ANIMAL_CELLS
        if p not in reserved
        and isinstance(_tile(board, p), dict)
        and _tile(board, p).get("animal")
    ]
    need_feed = [p for p in animals if day <= 28 and not _tile(board, p).get("fed_today", False)]

    # At the start of each day, take enough wheat for several feed rounds.
    if need_feed and _count(inv, "WHEAT") == 0 and _count(shed, "WHEAT") > 0:
        if tuple(pos) in SHED_TILES:
            return ["PICKUP", "WHEAT", min(4, _count(shed, "WHEAT"))]
        return _move_toward(pos, _nearest(pos, list(SHED_TILES)))

    priorities = [
        [p for p in animals if day <= 28 and not _tile(board, p).get("fed_today", False) and _count(inv, "WHEAT") > 0],
        [p for p in animals if _tile(board, p).get("yield_units", 0) > 0],
        [p for p in animals if day <= 28 and not _tile(board, p).get("cared_today", False)],
        [p for p in animals if day <= 28 and _tile(board, p).get("fertilizer_available", False)],
    ]
    for candidates in priorities:
        if candidates:
            target = _nearest(pos, candidates)
            reserved.add(target)
            if pos != target:
                return _move_toward(pos, target)
            tile = _tile(board, target)
            if day <= 28 and not tile.get("fed_today", False) and _count(inv, "WHEAT") > 0:
                return ["FEED"]
            if tile.get("yield_units", 0) > 0:
                return ["HARVEST"]
            if day <= 28 and not tile.get("cared_today", False):
                return ["CARE"]
            if day <= 28 and tile.get("fertilizer_available", False):
                return ["COLLECT_FERTILIZER"]
    return None


def _crop_action(
    pos, inv, board, seeds, reserved, day, prices, prefer_wheat,
    diversification_enabled, strawberry_enabled, own_crop_counts,
    opponent_crop_counts, assigned_cells=None,
):
    """Greedy crop maintenance, harvest, and alternating wheat/carrot planting."""
    crop_cells = assigned_cells or CROP_CELLS
    here = _tile(board, pos)
    if isinstance(here, dict) and here.get("kind") == "WEED":
        return ["DIG"]
    if isinstance(here, dict) and here.get("kind") == "PLANT":
        crop = here.get("crop")
        first_day = {
            "WHEAT": 2, "CARROT": 2, "TOMATO": 8,
            "STRAWBERRY": 10, "MELON": 10,
        }.get(crop, 99)
        harvest_day = {
            "WHEAT": 4, "CARROT": 3, "TOMATO": 8,
            "STRAWBERRY": 10, "MELON": 10,
        }.get(crop, 99)
        age = day - int(here.get("planted_day", day))
        ongoing = crop in ("TOMATO", "STRAWBERRY")
        if (
            here.get("yield_units", 0) > 0
            and age >= harvest_day
            and (ongoing or here.get("watered_today", False))
        ):
            return ["HARVEST"]
        if not here.get("watered_today", False):
            return ["WATER"]

    plants = [
        p for p in crop_cells
        if p not in reserved
        and isinstance(_tile(board, p), dict)
        and _tile(board, p).get("kind") == "PLANT"
    ]
    urgent = [
        p for p in plants
        if not _tile(board, p).get("watered_today", False)
        and _tile(board, p).get("consecutive_unwatered", 0) >= 1
    ]
    harvestable = [
        p for p in plants
        if _tile(board, p).get("yield_units", 0) > 0
        and day - int(_tile(board, p).get("planted_day", day)) >= {
            "WHEAT": 4, "CARROT": 3, "TOMATO": 8,
            "STRAWBERRY": 10, "MELON": 10,
        }.get(_tile(board, p).get("crop"), 99)
        and (
            _tile(board, p).get("crop") in ("TOMATO", "STRAWBERRY")
            or _tile(board, p).get("watered_today", False)
        )
    ]
    needs_water = [p for p in plants if not _tile(board, p).get("watered_today", False)]
    weeds = [
        p for p in crop_cells
        if p not in reserved
        and isinstance(_tile(board, p), dict)
        and _tile(board, p).get("kind") == "WEED"
    ]

    for candidates, op in (
        (urgent, "WATER"),
        (harvestable, "HARVEST"),
        (needs_water, "WATER"),
        (weeds, "DIG"),
    ):
        if candidates:
            target = _nearest(pos, candidates)
            reserved.add(target)
            return [op] if pos == target else _move_toward(pos, target)

    # Stop on day 26 so the last crop is harvested/deposited before the final day.
    empties = [p for p in crop_cells if day <= 26 and p not in reserved and _tile(board, p) is None]
    if empties:
        # Development order is defined by shed distance, not worker proximity.
        target = min(
            empties,
            key=lambda p: (
                _home_distance(p),
                -_quadrant_occupancy(board, p),
                p[1],
                p[0],
            ),
        )
        crop = _preferred_crop(
            day, prices, prefer_wheat, own_crop_counts, opponent_crop_counts,
        )
        if _count(seeds, crop) == 0:
            viable_stock = [
                item for item in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
                if _count(seeds, item) > 0 and _crop_can_finish(item, day)
            ]
            crop = viable_stock[0] if viable_stock else "WHEAT"
        if _count(seeds, crop) > 0:
            reserved.add(target)
            return ["PLANT", crop] if pos == target else _move_toward(pos, target)
    return None


def _required_total_workers(board, day, money, seed_stock):
    """Size the workforce from live crop, livestock, and setup workload."""
    animals = [
        _tile(board, p) for p in ANIMAL_CELLS
        if isinstance(_tile(board, p), dict) and _tile(board, p).get("animal")
    ]
    plants = [
        _tile(board, p) for p in CROP_CELLS
        if isinstance(_tile(board, p), dict) and _tile(board, p).get("kind") == "PLANT"
    ]
    empty_animal_cells = sum(
        _tile(board, p) is None and p not in GOOSE_CELLS for p in ANIMAL_CELLS
    )
    empty_structures = sum(
        isinstance(_tile(board, p), dict)
        and _tile(board, p).get("kind") in ("PASTURE", "COOP")
        and not _tile(board, p).get("animal")
        for p in ANIMAL_CELLS
    )
    due_now = 0
    due_now += sum(not a.get("fed_today", False) for a in animals)
    due_now += sum(a.get("yield_units", 0) > 0 for a in animals)
    if day <= 28:
        due_now += sum(not a.get("cared_today", False) for a in animals)
        due_now += sum(a.get("fertilizer_available", False) for a in animals)
    due_now += sum(not p.get("watered_today", False) for p in plants)
    due_now += sum(p.get("yield_units", 0) > 0 for p in plants)
    active_capacity = sum(_tile(board, p) != "LOCKED" for p in CROP_CELLS)

    # Recurring daily capacity: an animal can require feed, care, harvest and
    # fertilizer collection; every crop needs water and periodically harvest.
    recurring = 4 * len(animals) + (3 * len(plants) + 1) // 2
    # Moving between nearby jobs consumes roughly one action per two occupied tiles.
    recurring += (len(animals) + len(plants) + 1) // 2

    # While filling the farm, reserve capacity for construction and planting.
    setup = 0
    if day <= 26:
        crop_slots_to_fill = max(0, active_capacity - len(plants))
        # Every open slot represents a dig/plant trip; counting only a small
        # prefix makes staffing react too slowly after a land purchase.
        setup += 2 * crop_slots_to_fill
        setup += 2 * empty_animal_cells + 2 * empty_structures

    # Convert cash into plantable capacity before staffing it. Keep a livestock
    # operating buffer so an aggressive fill never prevents feed purchases.
    open_crop_slots = max(0, active_capacity - len(plants))
    operating_buffer = 200 + 30 * len(animals)
    affordable_seed_units = max(0, int(money - operating_buffer) // 10)
    funded_open_slots = min(open_crop_slots, seed_stock + affordable_seed_units)
    planned_plants = (
        len(plants) + funded_open_slots if day <= 26 else len(plants)
    )
    count_based = (
        40 + 12 * len(animals) + 6 * planned_plants + 39
    ) // 40

    # Use whichever is larger: population load or today's observed/setup backlog.
    estimated_actions = max(recurring, due_now + setup)
    estimated_actions += 3  # shed pickup/drop and imperfect routing allowance
    # Setup work has substantially more routing overhead than a compact sweep.
    effective_actions_per_worker = 14 if setup > 0 else 18
    backlog_based = (
        estimated_actions + effective_actions_per_worker - 1
    ) // effective_actions_per_worker
    total = max(count_based, backlog_based)
    if day <= 1:
        total = max(total, 3)
    if day == 29:
        # Retain enough carriers for liquidation, without paying for field upkeep.
        total = max(2, (len(animals) + len(plants) + 11) // 12)
    total = max(1, min(12, total))

    # Hiring costs follow 1,1,2,3,5... each day. Do not request a crew whose
    # cumulative wage would consume the cash reserved for planting/feeding.
    wage_budget = max(0, int(money - operating_buffer))
    fib_a, fib_b = 1, 1
    wage_sum = 0
    affordable_hands = 0
    for _ in range(total - 1):
        next_cost = fib_a
        if wage_sum + next_cost > wage_budget:
            break
        wage_sum += next_cost
        affordable_hands += 1
        fib_a, fib_b = fib_b, fib_a + fib_b
    return 1 + affordable_hands


def agent(obs):
    player = int(obs["player"])
    me = obs["farms"][player]
    private = obs["private"]
    board = me["tiles"]
    opponent_board = obs["farms"][1 - player]["tiles"]
    shed = private["shed"]
    seeds = private["seeds"]
    inventories = private["inventories"]
    day = int(obs["day"])
    hour = int(obs["hour"])
    step = int(obs.get("step", day * 24 + hour))
    prices = obs["market"]["prices"]
    crop_names = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
    own_crop_counts = {
        crop: sum(
            isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop
            for row in board for tile in row
        )
        for crop in crop_names
    }
    opponent_crop_counts = {
        crop: sum(
            isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop
            for row in opponent_board for tile in row
        )
        for crop in crop_names
    }
    unlocked_quadrants = set(me.get("unlocked_quadrants", []))
    ne_unlocked = "NE" in unlocked_quadrants
    sw_unlocked = "SW" in unlocked_quadrants
    se_unlocked = "SE" in unlocked_quadrants
    diversification_enabled = (
        day >= 5
        and
        day <= 12
        and me["money"] >= 1500
    )
    strawberry_enabled = diversification_enabled and _strawberry_viable(prices)

    market = []
    # Sell all completed goods already deposited in the shed.
    sell_items = ["CARROT", "EGG", "FERTILIZER", "TOMATO", "STRAWBERRY", "MELON", "MILK", "WOOL"]
    if day == 29:
        sell_items.append("WHEAT")
    for item in sell_items:
        qty = _count(shed, item)
        if qty > 0:
            market.append(["SELL", item, qty])

    plants = sum(
        1 for p in CROP_CELLS
        if isinstance(_tile(board, p), dict) and _tile(board, p).get("kind") == "PLANT"
    )
    active_crop_capacity = sum(_tile(board, p) != "LOCKED" for p in CROP_CELLS)
    seed_items = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
    seed_total = sum(_count(seeds, item) for item in seed_items)
    if step == 0:
        market.extend([
            ["BUY_ANIMAL", "COW", 3],
            ["BUY_ANIMAL", "SHEEP", 2],
            ["BUY_PRODUCT", "WHEAT", 8],
            ["BUY_SEED", "WHEAT", 12],
        ])
    # First horizontal expansion: land + a replicated five-animal unit.
    if not ne_unlocked and day <= 14 and me["money"] >= 5000:
        market.append(["BUY_LAND"])
    # Later quadrants are crop-only. Buy at the earliest conservative payback
    # point, but only after the preceding unit is substantially occupied.
    elif (
        ne_unlocked
        and not sw_unlocked
        # New land has marginal value only when existing crop space is the
        # bottleneck. Livestock cells are excluded from this utilization test.
        and _plant_count(board, NW_CROP_CELLS + NE_CROP_CELLS) >= 28
        and _crop_land_is_profitable(day, prices, 2000, me["money"])
    ):
        market.append(["BUY_LAND"])
    # Do not buy SE yet: the ten daily hire-order slots can fully staff three
    # quadrants plus livestock, but a fourth quadrant would remain mostly idle.

    placed_animals = sum(
        bool(isinstance(_tile(board, p), dict) and _tile(board, p).get("animal"))
        for p in ANIMAL_CELLS
    )
    wheat_target = max(8, placed_animals * 2)
    wheat_available = _count(shed, "WHEAT") + sum(_count(inv, "WHEAT") for inv in inventories)
    feed_threshold = max(10, placed_animals * (5 if day < 14 else 2))
    prefer_wheat = wheat_available < feed_threshold

    if step > 0 and day <= 26 and plants + seed_total < active_crop_capacity and me["money"] >= 100:
        fill_gap = active_crop_capacity - plants - seed_total
        seed_cost = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
        seed_cash = max(0, int(me["money"] - (300 + 50 * placed_animals)))
        scores = _crop_scores(
            day, prices, own_crop_counts, opponent_crop_counts, prefer_wheat,
        )
        affordable = [
            crop for crop in scores
            if seed_cash >= seed_cost[crop] and _crop_can_finish(crop, day)
        ]
        if affordable:
            buy_crop = max(affordable, key=scores.get)
            batch = min(8, fill_gap, seed_cash // seed_cost[buy_crop])
            if batch > 0:
                market.append(["BUY_SEED", buy_crop, batch])

    if day <= 28 and wheat_available < wheat_target and me["money"] >= 400:
        market.append(["BUY_PRODUCT", "WHEAT", max(1, wheat_target - wheat_available)])

    # Twelve animals form the stable base. One or two optional SW slots are
    # activated from live prices, remaining production, and visible opposition.
    if ne_unlocked and day <= 16:
        cows = _owned_count(board, shed, inventories, "COW")
        sheep = _owned_count(board, shed, inventories, "SHEEP")
        operating_buffer = 1000 + placed_animals * 75
        cow_target = 7 if sw_unlocked else 6
        sheep_target = 5 if sw_unlocked else 4
        if sw_unlocked:
            opponent_cows = sum(
                isinstance(tile, dict) and tile.get("animal") == "COW"
                for row in opponent_board for tile in row
            )
            opponent_sheep = sum(
                isinstance(tile, dict) and tile.get("animal") == "SHEEP"
                for row in opponent_board for tile in row
            )
            crop_scores_now = _crop_scores(
                day, prices, own_crop_counts, opponent_crop_counts, False,
            )
            crop_daily_net = max(crop_scores_now.values(), default=0.0)
            marginal = {
                "COW": _animal_marginal_score(
                    "COW", day, prices, opponent_cows, crop_daily_net,
                ),
                "SHEEP": _animal_marginal_score(
                    "SHEEP", day, prices, opponent_sheep, crop_daily_net,
                ),
            }
            ranked = sorted(marginal, key=marginal.get, reverse=True)
            if marginal[ranked[0]] >= 300:
                if ranked[0] == "COW":
                    cow_target += 1
                else:
                    sheep_target += 1
            # The 14th head must stand on its own merits and must not be a much
            # weaker duplicate of the market's currently preferred livestock.
            if (
                marginal[ranked[1]] >= 650
                and marginal[ranked[1]] >= 0.55 * marginal[ranked[0]]
                and me["money"] >= operating_buffer + 2500
            ):
                if ranked[1] == "COW":
                    cow_target += 1
                else:
                    sheep_target += 1
            # Never abandon an optional animal after committing cash to it.
            cow_target = max(cow_target, min(cows, 8))
            sheep_target = max(sheep_target, min(sheep, 6))
        if sheep < sheep_target and me["money"] >= operating_buffer + 500:
            market.append(["BUY_ANIMAL", "SHEEP", 1])
        elif cows < cow_target and me["money"] >= operating_buffer + 400:
            market.append(["BUY_ANIMAL", "COW", 1])

    # Optional egg hedge: keep milk pressure, but add one goose only when the
    # opponent has no geese and the remaining egg stream repays feed + purchase.
    opponent_geese = sum(
        isinstance(tile, dict) and tile.get("animal") == "GOOSE"
        for row in opponent_board for tile in row
    )
    own_geese = _owned_count(board, shed, inventories, "GOOSE")
    if sw_unlocked and day <= 14 and own_geese == 0 and opponent_geese == 0:
        production_days = max(0, 29 - day - 4)
        egg_gross = production_days * float(prices.get("EGG", 50))
        feed_cost = (29 - day) * float(prices.get("WHEAT", 25))
        if production_days >= 8 and egg_gross - feed_cost >= 450 and me["money"] >= 2500:
            market.append(["BUY_ANIMAL", "GOOSE", 1])


    # Hire only the capacity implied by today's measurable workload.
    if hour == 0:
        desired_hands = _required_total_workers(
            board, day, me["money"], seed_total,
        ) - 1
        # Hands exist for one day only. Reserve the market-order slots for the
        # calculated crew; ordinary sales and purchases resume next turn.
        market = [["HIRE"] for _ in range(max(0, desired_hands))] + market
    market = market[:10]

    positions = [me["farmer"]] + list(me.get("hands", []))
    livestock_leads = 3 if sw_unlocked else (2 if ne_unlocked else 1)
    crop_worker_count = max(1, len(positions) - livestock_leads)
    unlocked_crop_groups = [
        sorted(group, key=lambda p: (_home_distance(p), p[1], p[0]))
        for group in CROP_GROUPS
        if any(_tile(board, p) != "LOCKED" for p in group)
    ]
    group_count = len(unlocked_crop_groups)
    if group_count == 1:
        crop_quotas = [crop_worker_count]
    elif group_count == 2:
        left = crop_worker_count // 2
        crop_quotas = [left, crop_worker_count - left]
    else:
        # Mature northern units need two maintainers each; concentrate all
        # remaining hands on the newly purchased crop-only SW quadrant.
        north_each = 2 if crop_worker_count >= 7 else 1
        crop_quotas = [north_each, north_each, crop_worker_count - 2 * north_each]
    reserved = set()
    actions = []
    for index, pos_list in enumerate(positions):
        pos = tuple(pos_list)
        inv = inventories[index] if index < len(inventories) else {}
        # One livestock lead per unlocked five-animal unit.
        action = None
        # Final-day products must enter the shed before a later market order can sell them.
        if day == 29 and any(_count(inv, item) > 0 for item in PRODUCTS):
            action = ["DROP"] if pos in SHED_TILES else _move_toward(pos, _nearest(pos, list(SHED_TILES)))
        action = action or _urgent_feed_action(pos, inv, board, shed, reserved, day)
        if index < livestock_leads:
            action = action or _animal_action(pos, inv, board, shed, reserved, day)
        if action is None:
            crop_slot = max(0, index - livestock_leads)
            running = 0
            group_index = 0
            lane = 0
            for candidate_group, quota in enumerate(crop_quotas):
                if crop_slot < running + quota:
                    group_index = candidate_group
                    lane = crop_slot - running
                    break
                running += quota
            else:
                group_index = group_count - 1
                lane = max(0, crop_quotas[-1] - 1)
            assigned_cells = _lane_chunk(
                unlocked_crop_groups[group_index], lane, max(1, crop_quotas[group_index]),
            )
            action = _crop_action(
                pos, inv, board, seeds, reserved, day, prices,
                prefer_wheat, diversification_enabled, strawberry_enabled,
                own_crop_counts, opponent_crop_counts,
                assigned_cells,
            )
        # Crop hands help with overdue animal care after crop work is exhausted.
        if action is None:
            action = _animal_action(pos, inv, board, shed, reserved, day)
        actions.append(action or ["PASS"])

    return {
        "farmer": actions[0],
        "hands": actions[1:],
        "market": market,
    }
