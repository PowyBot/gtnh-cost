"""Quanto costa davvero un oggetto GTNH in materie prime.

Ogni oggetto ha un costo = minimo, sulle ricette che lo producono, di (costo input + energia + passo) / quantità.
Si calcola col Dijkstra generalizzato di Knuth sugli iperarchi: una ricetta "scatta" quando tutti i suoi input
hanno costo definitivo, quindi i cicli (lingotto ↔ polvere, pacchetti, ...) non abbassano mai i costi.
Poi si espande l'albero delle ricette scelte fino alle materie prime.

uso: python3 cost.py "LV Machine Hull" [quantità] [--tier MV]
     python3 cost.py --find hull
--tier limita le ricette a quelle fattibili fino a quel tier: Stone, Steam, ULV, LV, ... (default: tutte, anche end-game).
"""
import heapq
import os
import pickle
import re
import sys
from collections import defaultdict

DATA = "/home/enn3/projects/gtnh-cost/recipes.pkl"
EU_WEIGHT = 1e-5      # 100k EU = 1 materia prima
STEP = 0.02           # ogni ricetta costa un po': a parità preferisce catene corte
FLUID_UNIT = 1000.0   # 1000 L di fluido = 1 oggetto
INF = float("inf")
SWEEPS = 8            # passate di miglioramento dopo Knuth
UNKNOWN = 1000.0      # oggetti che nessuna ricetta produce e che non so raccogliere: ultima spiaggia
# Vis ed essentia di Thaumcraft non sono nel modello: ogni ricetta magica costa una cifra fissa in più.
MAGIC = {"Thaumcraft Arcane Crafting": 0.5, "Thaumcraft Crucible": 1.0, "Thaumcraft Infusion": 4.0}

# Cose che si raccolgono nel mondo anche se qualche ricetta le produce (sennò i cicli le lasciano senza costo).
GATHERED = re.compile(
    r"^(gregtech:gt\.blockores\d*@|minecraft:(cobblestone|stone|sand|gravel|dirt|log2?|clay_ball|clay|netherrack|"
    r"end_stone|obsidian|soul_sand|snowball|ice|reeds|cactus|wheat_seeds|leaves2?|sapling|"
    r"(iron|gold|diamond|emerald|coal|redstone|lapis|quartz)_ore|"
    r"slime_ball|string|bone|feather|leather|ender_pearl|blaze_rod|gunpowder|spider_eye|rotten_flesh|ghast_tear|"
    r"glowstone_dust|wool|egg|vine|waterlily|pumpkin|melon|red_flower|yellow_flower|brown_mushroom|red_mushroom)"
    r"(@\d+)?$|ic2:itemharz$|ic2:blockrubwood|"
    r"water$|lava$|oxygen$|nitrogen$|air$|gregtech:gt\.blockgranites|bartworks:bw\.blockores|"
    r"gtplusplus:.*ore)"
)


def load():
    return pickle.load(open(DATA, "rb"))


def unit(kinds, item):
    return FLUID_UNIT if kinds.get(item) == "fluid" else 1.0


TIERS = ["Stone", "Steam", "ULV", "LV", "MV", "HV", "EV", "IV", "LuV", "ZPM", "UV", "UHV", "UEV", "UIV", "UMV", "UXV", "OpV", "MAX"]
STONE, STEAM, ULV, LV = range(4)
# build.py stores the export's minimumTier as an index into ["NONE", "ULV", "LV", ...]
VOLTAGE_TO_TIER = 1

# No machines at all, or primitive blocks built from bricks and clay.
STONE_MACHINES = {"Shaped Crafting", "Shapeless Crafting", "Furnace", "Cauldron", "Coke Oven", "Bricked Blast Furnace"}
# Bronze (normal) and steel (high pressure) single blocks, plus the GT++ steam multiblocks.
STEAM_MACHINES = {
    *(f"{pressure}Steam {m}" for pressure in ("", "High Pressure ")
      for m in ("Macerator", "Compressor", "Extractor", "Forge Hammer", "Alloy Smelter", "Furnace")),
    "Steam Grinder", "Steam Squasher", "Steam Separator", "Steam Presser", "Steam Purifier", "Steam Blender",
    "Steam Fuser", "Steam Hearth",
}
# Steam machines look recipes up at LV voltage (MTEBasicMachineBronze.checkRecipe in GT5-Unofficial,
# https://github.com/GTNewHorizons/GT5-Unofficial), so they run anything up to 32 EU/t of their recipe map.
STEAM_MAX_EUT = 32
# The export lists these without machineHandlers, so build.py can't tell they are multiblocks.
# All have ULV-voltage recipes but need LV+ parts to build.
UNMARKED_MULTIBLOCKS = {
    "Chemical Plant", "Nanochip Conversion Complex", "Component Assembly Line", "Extreme Heat Exchanger",
    "Bacterial Vat", "Multiblock Dehydrator", "Nuclear Fission", "Neutron Activator", "High Temperature Gas Reactor",
    "Foundry Module Components", "Liquid Fluoride Thorium Reactor",
}


def recipe_tier(recipe, multiblocks):
    machine, _, _, _, voltage, eut, _, handlers = recipe
    if machine in STONE_MACHINES:
        return STONE
    # Thaumcraft has no GT tier: placed in steam age by eye, it's not something you do with just a crafting table.
    if machine in MAGIC or (eut <= STEAM_MAX_EUT and any(h in STEAM_MACHINES for h in handlers)):
        return STEAM
    single_block = any(h not in multiblocks for h in handlers) if handlers else machine not in UNMARKED_MULTIBLOCKS
    if voltage + VOLTAGE_TO_TIER <= ULV and single_block:
        return ULV
    # The voltage alone used to decide, so ULV filled up with 8 EU/t recipes of LV+ multiblocks.
    return max(voltage + VOLTAGE_TO_TIER, LV)


def solve(data, max_tier=len(TIERS)):
    recipes, kinds = data["recipes"], data["kinds"]
    allowed = [recipe_tier(r, data["multiblocks"]) <= max_tier for r in recipes]
    produced = {o for r, ok in zip(recipes, allowed) if ok for o, _ in r[3]}
    used_by = defaultdict(list)
    for idx, r in enumerate(recipes):
        if not allowed[idx]:
            continue
        for slot_ids, _ in r[2]:
            for item in slot_ids:
                used_by[item].append(idx)

    cost, choice, done = {}, {}, set()
    waiting = [len(r[2]) if ok else -1 for r, ok in zip(recipes, allowed)]
    slot_done = [[False] * len(r[2]) for r in recipes]
    heap = []

    def offer(item, value, how):
        if item in done or value >= cost.get(item, INF):
            return
        cost[item], choice[item] = value, how
        heapq.heappush(heap, (value, item))

    for item in set(kinds) | produced:
        if GATHERED.search(item):
            offer(item, data["ores"].get(data["names"].get(item), 1.0) / unit(kinds, item), "raw")
        elif item not in produced:
            offer(item, UNKNOWN / unit(kinds, item), "raw")

    # 1) Dijkstra generalizzato (Knuth): una ricetta scatta quando tutti gli input hanno costo definitivo.
    while heap:
        value, item = heapq.heappop(heap)
        if item in done or value > cost[item]:
            continue
        done.add(item)
        for idx in used_by[item]:
            for s, (ids, _) in enumerate(recipes[idx][2]):
                if slot_done[idx][s] or item not in ids:
                    continue
                slot_done[idx][s] = True
                waiting[idx] -= 1
            if waiting[idx] == 0:
                waiting[idx] = -1
                for out, value in outputs_cost(recipes[idx], cost):
                    offer(out, value, idx)

    # 2) Knuth vale solo se un prodotto costa più dei suoi ingredienti; in GT no (1 minerale -> 3 polveri),
    #    quindi qualcosa è stato chiuso troppo presto. Passate di rilassamento, accettando un ribasso
    #    solo se la ricetta non dipende (tramite le scelte attuali) dall'oggetto stesso: niente cicli.
    for _ in range(SWEEPS):
        changed = 0
        for idx, r in enumerate(recipes):
            if not allowed[idx]:
                continue
            for out, value in outputs_cost(r, cost):
                if value < cost.get(out, INF) * (1 - 1e-6) and not depends_on(recipes, cost, choice, idx, out):
                    cost[out], choice[out] = value, idx
                    changed += 1
        if not changed:
            break
    return cost, choice


def cheapest(ids, cost):
    return min(ids, key=lambda i: cost.get(i, INF))


def outputs_cost(recipe, cost):
    machine, eu, inputs, outputs = recipe[:4]
    total = STEP + eu * EU_WEIGHT + MAGIC.get(machine, 0.0) + sum(amount * cost.get(cheapest(ids, cost), INF) for ids, amount in inputs)
    return [(item, total / amount) for item, amount in outputs if amount > 0 and total < INF]


def depends_on(recipes, cost, choice, idx, target):
    stack, seen = [cheapest(ids, cost) for ids, _ in recipes[idx][2]], set()
    while stack:
        item = stack.pop()
        if item == target:
            return True
        how = choice.get(item)
        if item in seen or how is None or how == "raw":
            continue
        seen.add(item)
        stack.extend(cheapest(ids, cost) for ids, _ in recipes[how][2])
    return False


def expand(data, cost, choice, item, amount, raw, steps, path=()):
    how = choice.get(item)
    if how is None or how == "raw" or item in path:
        raw[item] += amount
        return
    machine, _, inputs, outputs = data["recipes"][how][:4]
    made = next(a for o, a in outputs if o == item)
    runs = amount / made
    steps[(machine, item)] += runs
    for ids, need in inputs:
        best = cheapest(ids, cost)
        expand(data, cost, choice, best, need * runs, raw, steps, path + (item,))


def find(data, text):
    text = text.lower()
    return sorted((n, i) for i, n in data["names"].items() if text in n.lower())


def pick(data, cost, query):
    if query in data["names"]:
        return query
    exact = [i for n, i in find(data, query) if n.lower() == query.lower()]
    candidates = exact or [i for _, i in find(data, query)]
    reachable = [i for i in candidates if i in cost]
    return min(reachable, key=lambda i: cost[i]) if reachable else None


def show(data, cost, choice, item, amount):
    names, kinds = data["names"], data["kinds"]
    raw, steps = defaultdict(float), defaultdict(float)
    expand(data, cost, choice, item, amount, raw, steps)
    print(f"{amount:g} × {names.get(item, item)}  [{item}]  costo {cost[item] * amount:.2f}")
    print("\nmaterie prime:")
    for r, a in sorted(raw.items(), key=lambda kv: -kv[1] * cost.get(kv[0], 1)):
        label = f"{a:.0f} L" if kinds.get(r) == "fluid" else f"{a:.2f}".rstrip("0").rstrip(".")
        unknown = "" if GATHERED.search(r) else "  (?) nessuna ricetta: da trovare/comprare"
        print(f"  {label:>10}  {names.get(r, r)}{unknown}")
    print(f"\npassi ({len(steps)} ricette diverse):")
    for (machine, out), runs in sorted(steps.items(), key=lambda kv: kv[0][0]):
        print(f"  {runs:8.2f} × {machine}: {names.get(out, out)}")


def cached_solve(data, max_tier):
    path = f"{DATA[:-4]}-{TIERS[min(max_tier, len(TIERS) - 1)]}.cache.pkl"
    stamp = (os.path.getmtime(DATA), os.path.getmtime(__file__))
    if os.path.exists(path):
        cached = pickle.load(open(path, "rb"))
        if cached["stamp"] == stamp:
            return cached["cost"], cached["choice"]
    cost, choice = solve(data, max_tier)
    pickle.dump({"stamp": stamp, "cost": cost, "choice": choice}, open(path, "wb"))
    return cost, choice


def main(argv):
    data = load()
    if argv[:1] == ["--find"]:
        for n, i in find(data, " ".join(argv[1:]))[:40]:
            print(f"{n}  [{i}]")
        return 0
    max_tier = len(TIERS)
    if "--tier" in argv:
        at = argv.index("--tier")
        max_tier = [t.lower() for t in TIERS].index(argv[at + 1].lower())
        argv = argv[:at] + argv[at + 2:]
    cost, choice = cached_solve(data, max_tier)
    amount = float(argv[1]) if len(argv) > 1 else 1.0
    item = pick(data, cost, argv[0])
    if item is None:
        print(f"non trovo (o non so fare) '{argv[0]}'")
        return 1
    show(data, cost, choice, item, amount)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
