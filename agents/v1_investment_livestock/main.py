"""Investment-first 5x5 baseline: cows/sheep plus short-cycle crops.

It concentrates early cash into recurring livestock production, sizes the daily
workforce from estimated workload, sweeps from the shed toward the field edge,
and stops investments near season end. It deliberately does not buy land yet.
"""

PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
SHED_TILES = {(4, 4), (5, 4), (4, 5), (5, 5)}
ANIMAL_CELLS = [(3, 4), (4, 3), (3, 3)]
DESIRED_ANIMAL = {(3, 4): "COW", (4, 3): "COW", (3, 3): "SHEEP"}
CROP_CELLS = [
    (x, y)
    for y in range(5)
    for x in range(5)
    if (x, y) not in ANIMAL_CELLS and (x, y) != (4, 4)
]


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


def _animal_action(pos, inv, board, shed, reserved, day):
    """Return an animal-oriented action and reserve its selected target."""
    here = _tile(board, pos)

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

    # Empty pastures need their designated cow or sheep carried from the shed.
    empty_structures = [
        p for p in ANIMAL_CELLS
        if p not in reserved
        and isinstance(_tile(board, p), dict)
        and _tile(board, p).get("kind") == "PASTURE"
        and not _tile(board, p).get("animal")
    ]
    for animal in ("COW", "SHEEP"):
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
        p for p in ANIMAL_CELLS if p not in reserved and _tile(board, p) is None
    ]
    if build_cells:
        target = _nearest(pos, build_cells)
        reserved.add(target)
        return ["BUILD_PASTURE"] if pos == target else _move_toward(pos, target)

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


def _crop_action(pos, inv, board, seeds, reserved, day):
    """Greedy crop maintenance, harvest, and alternating wheat/carrot planting."""
    here = _tile(board, pos)
    if isinstance(here, dict) and here.get("kind") == "WEED":
        return ["DIG"]
    if isinstance(here, dict) and here.get("kind") == "PLANT":
        crop = here.get("crop")
        first_day = 2 if crop in ("WHEAT", "CARROT") else 99
        age = day - int(here.get("planted_day", day))
        if here.get("yield_units", 0) > 0 and age >= first_day:
            return ["HARVEST"]
        if not here.get("watered_today", False):
            return ["WATER"]

    plants = [
        p for p in CROP_CELLS
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
        and day - int(_tile(board, p).get("planted_day", day)) >= 2
    ]
    needs_water = [p for p in plants if not _tile(board, p).get("watered_today", False)]
    weeds = [
        p for p in CROP_CELLS
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
    empties = [p for p in CROP_CELLS if day <= 26 and p not in reserved and _tile(board, p) is None]
    if empties:
        target = _nearest(pos, empties)
        crop = "CARROT" if (target[0] + target[1]) % 2 else "WHEAT"
        if _count(seeds, crop) == 0:
            crop = "WHEAT" if crop == "CARROT" else "CARROT"
        if _count(seeds, crop) > 0:
            reserved.add(target)
            return ["PLANT", crop] if pos == target else _move_toward(pos, target)
    return None


def _required_total_workers(board, day):
    """Estimate workers from productive actions plus a conservative travel buffer."""
    animals = [
        _tile(board, p) for p in ANIMAL_CELLS
        if isinstance(_tile(board, p), dict) and _tile(board, p).get("animal")
    ]
    plants = [
        _tile(board, p) for p in CROP_CELLS
        if isinstance(_tile(board, p), dict) and _tile(board, p).get("kind") == "PLANT"
    ]
    empty_animal_cells = sum(_tile(board, p) is None for p in ANIMAL_CELLS)
    empty_structures = sum(
        isinstance(_tile(board, p), dict)
        and _tile(board, p).get("kind") == "PASTURE"
        and not _tile(board, p).get("animal")
        for p in ANIMAL_CELLS
    )
    required = 0
    required += sum(not a.get("fed_today", False) for a in animals)
    required += sum(a.get("yield_units", 0) > 0 for a in animals)
    if day <= 28:
        required += sum(not a.get("cared_today", False) for a in animals)
        required += sum(a.get("fertilizer_available", False) for a in animals)
    required += sum(not p.get("watered_today", False) for p in plants)
    required += sum(p.get("yield_units", 0) > 0 for p in plants)
    required += 2 * min(4, max(0, 12 - len(plants))) if day <= 26 else 0
    required += 2 * empty_animal_cells + 2 * empty_structures
    # A shed-to-edge sweep is short, but setup and transitions still cost moves.
    travel_buffer = 4 + (len(animals) + len(plants) + 3) // 4
    effective_actions_per_worker = 18
    total = (required + travel_buffer + effective_actions_per_worker - 1) // effective_actions_per_worker
    if day <= 1:
        total = max(total, 3)
    return max(1, min(5, total))


def agent(obs):
    player = int(obs["player"])
    me = obs["farms"][player]
    private = obs["private"]
    board = me["tiles"]
    shed = private["shed"]
    seeds = private["seeds"]
    inventories = private["inventories"]
    day = int(obs["day"])
    hour = int(obs["hour"])
    step = int(obs.get("step", day * 24 + hour))

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
    seed_total = _count(seeds, "WHEAT") + _count(seeds, "CARROT")
    if step == 0:
        market.extend([
            ["BUY_ANIMAL", "COW", 2],
            ["BUY_ANIMAL", "SHEEP", 1],
            ["BUY_PRODUCT", "WHEAT", 30],
            ["BUY_SEED", "WHEAT", 8],
            ["BUY_SEED", "CARROT", 8],
        ])
    elif day <= 26 and plants + seed_total < 14 and me["money"] >= 100:
        market.extend([
            ["BUY_SEED", "WHEAT", 3],
            ["BUY_SEED", "CARROT", 3],
        ])
    if day <= 28 and _count(shed, "WHEAT") < 12 and me["money"] >= 200:
        market.append(["BUY_PRODUCT", "WHEAT", 12])

    # Hire only the capacity implied by today's measurable workload.
    if hour == 0:
        desired_hands = _required_total_workers(board, day) - 1
        market.extend([["HIRE"] for _ in range(max(0, desired_hands))])
    market = market[:10]

    positions = [me["farmer"]] + list(me.get("hands", []))
    reserved = set()
    actions = []
    for index, pos_list in enumerate(positions):
        pos = tuple(pos_list)
        inv = inventories[index] if index < len(inventories) else {}
        # Farmer and first hand start at shed-side livestock, then sweep outward.
        action = None
        # Final-day products must enter the shed before a later market order can sell them.
        if day == 29 and any(_count(inv, item) > 0 for item in PRODUCTS):
            action = ["DROP"] if pos in SHED_TILES else _move_toward(pos, _nearest(pos, list(SHED_TILES)))
        if index <= 1:
            action = action or _animal_action(pos, inv, board, shed, reserved, day)
        if action is None:
            action = _crop_action(pos, inv, board, seeds, reserved, day)
        # Crop hands help with overdue animal care after crop work is exhausted.
        if action is None:
            action = _animal_action(pos, inv, board, shed, reserved, day)
        actions.append(action or ["PASS"])

    return {
        "farmer": actions[0],
        "hands": actions[1:],
        "market": market,
    }
