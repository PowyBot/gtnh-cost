"""Quanto costa davvero un oggetto GTNH in materie prime.

Ogni oggetto ha un costo = minimo, sulle ricette che lo producono, di (costo input + energia + passo) / quantità.
Si calcola col Dijkstra generalizzato di Knuth sugli iperarchi: una ricetta "scatta" quando tutti i suoi input
hanno costo definitivo, quindi i cicli (lingotto ↔ polvere, pacchetti, ...) non abbassano mai i costi.
Poi si espande l'albero delle ricette scelte fino alle materie prime.

uso: python3 cost.py "LV Machine Hull" [quantità] [--tier MV] [--real]
     python3 cost.py --find hull
--tier limita le ricette a quelle fattibili fino a quel tier: Stone, Steam, ULV, LV, ... (default: tutte, anche end-game).
--real sceglie le ricette "da giocatore": pesa energia e tempo e penalizza le macchine rare (STANDARD_MAPS, UNUSUAL_MAPS).
"""
import heapq
import math
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
TRACE = 1e-6          # raw amounts below this per item made are hidden: dust left by long splitting chains
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
# Recipe maps whose controller is named differently; every other multiblock's controller has the map's name.
CONTROLLER_NAMES = {
    "Chemical Plant": "ExxonMobil Chemical Plant",
    "Nanochip Conversion Complex": "Nanochip Assembly Complex",
    "Multiblock Dehydrator": "Utupu-Tanuri",
    "Multiblock Electrolyzer": "Industrial Electrolyzer",
    "Nuclear Fission": "Nuclear Reactor",  # GT's fake map for IC2 reactor fuel rods
    "High Temperature Gas Reactor": "High Temperature Gas-cooled Reactor",
    "Foundry Module Components": "Exo-Foundry",
    "Milling": "IsaMill Grinding Machine",
    "DTPF": "Dimensionally Transcendent Plasma Forge",
    "Precise Assembler": "Precise Auto-Assembler MT-3662",
    "Condensate Entanglement": "Bose-Einstein Condensate Entanglement Apparatus",
    "Flotation Cell": "Flotation Cell Regulator",
    "Nuclear Fuel Processing": "Reactor Fuel Processing Plant",
    "LFTR Gas Sparging": "Sparge Tower Controller",
    "Clarifier": "Clarifier Purification Unit",
    "Ozonation": "Ozonation Purification Unit",
    "Flocculation": "Flocculation Purification Unit",
    "pH Neutralization": "pH Neutralization Purification Unit",
    "Temperature Fluctuation": "Extreme Temperature Fluctuation Purification Unit",
    "High Energy Laser Treatment": "High Energy Laser Purification Unit",
    "Degassing": "Residual Decontaminant Degasser Purification Unit",
    "Baryonic Perfection": "Absolute Baryonic Perfection Purification Unit",
}
# The export lists these without machineHandlers, so build.py can't tell they are multiblocks. Still treated as
# single blocks, for lack of a known controller: Vacuum Furnace, Part Processing Apparatus, Ice Cream Machine.
UNMARKED_MULTIBLOCKS = {
    *CONTROLLER_NAMES, "Component Assembly Line", "Extreme Heat Exchanger", "Bacterial Vat", "Neutron Activator",
    "Liquid Fluoride Thorium Reactor", "Helioflux Melting Core", "Electric Implosion Compressor",
    "Heliothermal Plasma Fabricator", "Target Chamber", "PCB Factory", "Circuit Assembly Line", "Industrial Coke Oven",
    "Pyrolyse Oven", "Solar Factory", "Nanochip Assembly Matrix", "Digester", "Dissolution Tank",
    "Nanoprecision Cutting Chamber", "Quantum Force Transformer", "Beam Crafter", "Nanoprecision Wire Tracer",
    "Draconic Evolution Fusion Crafter", "Nanometer Encasement Wrapper", "Nano Forge", "Naquadah Fuel Refinery",
    "Ultra-high Energy Etching Array", "Transcendent Plasma Mixer", "Boldarnator", "Optically Optimized Organizer",
    "Nuclear Salt Processing Plant", "Full-Board Immersion Device", "Superconductive Strand Splitter",
    "Accelerated Biological Coordinator", "Heliofusion Exoticizer", "Source Chamber", "COMET - Compact Cyclotron",
}

# Realistic mode: what a player actually builds. Picked by hand from the 125 recipe maps of the dataset: the GT
# single blocks every base has, the hand/furnace stuff, and the usual GT multiblocks (EBF, Vacuum Freezer, LCR, ...).
STANDARD_MAPS = {
    "Shaped Crafting", "Shapeless Crafting", "Furnace", "Cauldron", "Coke Oven", "Bricked Blast Furnace",
    "Fluid Solidifier", "Macerator", "Forge Hammer", "Extruder", "Fluid Extractor", "Assembler", "Alloy Smelter",
    "Arc Furnace", "Cutting Machine", "Canner", "Bending Machine", "Packager", "Unpackager", "Cable Coating",
    "Blast Furnace", "Centrifuge", "Laser Engraver", "Wiremill", "Chemical Reactor", "Lathe", "Compressor",
    "Chemical Bath", "Thermal Centrifuge", "Ore Washer", "Mixer", "Distillery", "Brewery", "Forming Press",
    "Electrolyzer", "Extractor", "Autoclave", "Circuit Assembler", "Electromagnetic Polarizer", "Sifter",
    "Oil Cracker", "Fermenter", "Electromagnetic Separator", "Fluid Heater",
    "Large Chemical Reactor", "Implosion Compressor", "Vacuum Freezer", "Distillation Tower", "Assemblyline Process",
    "Pyrolyse Oven", "Fusion Reactor", "Circuit Assembly Line", "PCB Factory",
}
# Machines a player builds for one job and then lives with, not something to reach for: the GT++ copies of
# standard maps with their own recipes (Multiblock Electrolyzer, Alloy Blast Smelter, ...), and single blocks
# off the usual path (Dehydrator, Bio Lab, ...). Everything not here and not standard counts as exotic.
UNUSUAL_MAPS = {
    "Multiblock Centrifuge", "Multiblock Mixer", "Multiblock Electrolyzer", "Multiblock Dehydrator", "Dehydrator",
    "Alloy Blast Smelter", "Chemical Plant", "Bio Lab", "Industrial Coke Oven", "Milling", "Flotation Cell",
    "Nuclear Fission", "Digester", "Dissolution Tank", "Bacterial Vat", "Neutron Activator", "Vacuum Furnace",
    "Electric Implosion Compressor", "Cold Trap", "Reactor Processing Unit", "Space Assembler",
    "Condensate Assembling", "Nanochip Conversion Complex", "Component Assembly Line", "Simple Dust Washer",
}
# Realistic cost of one recipe run, on top of its inputs, in the same unit as an overworld ore. By eye, tuned so that
# LV/HV hulls and circuits come out the way a player makes them: a standard step is nearly free, an unusual
# machine costs about one ore per run, an exotic one five, so only the end game reaches for them.
STANDARD_RUN, UNUSUAL_RUN, EXOTIC_RUN = 0.05, 1.0, 5.0
# Thaumcraft needs research and vis/essentia farms, none of which the model counts. At 5 per run a crucible that
# turns 1 ore into 4 Native Clusters still made redstone in an EV hull chain; by eye, 20 keeps it to the recipes
# only magic makes.
MAGIC_RUN = 20.0
# One overworld ore ≈ 50k EU: a coal ore gives 1-3 coal after processing, 16k EU each in an LV generator.
REAL_EU_WEIGHT = 2e-5
# Machine time per second: by eye, 100 s of one machine ≈ half an ore. Machines run in parallel in a real base,
# so time weighs little; it breaks ties toward the faster recipe.
REAL_SECOND_WEIGHT = 0.005
TICKS_PER_SECOND = 20
# Realistic price per 1000 L. Water and air are endless (a pump, a gas collector): only the machine time counts.
# Oxygen and nitrogen come out of air in a centrifuge. In the cheapest mode they cost 1 like any gathered thing,
# so electrolysing obsidian or phosphate dust "made" oxygen cheaper than breathing it.
REAL_FLUIDS = {"water": 0.05, "air": 0.05, "oxygen": 0.2, "nitrogen": 0.2}


NEVER = len(TIERS)


def recipe_tier(recipe, multiblocks, built):
    """built: multiblock -> first tier it can be built at (build_tiers)."""
    machine, _, _, _, voltage, eut, _, handlers = recipe
    if machine in STONE_MACHINES:
        return STONE
    # Thaumcraft has no GT tier: placed in steam age by eye, it's not something you do with just a crafting table.
    if machine in MAGIC or (eut <= STEAM_MAX_EUT and any(h in STEAM_MACHINES for h in handlers)):
        return STEAM
    machines = handlers or (machine,)
    if any(m not in multiblocks and m not in UNMARKED_MULTIBLOCKS for m in machines):
        # Assumed buildable at the recipe's voltage: a single block of that tier is made from that tier's parts.
        return max(voltage + VOLTAGE_TO_TIER, ULV)
    # The voltage alone used to decide, so 8 EU/t recipes of a Nuclear Fission or a Chemical Plant ran at ULV,
    # and at LV anything the export filed under an LV voltage, Component Assembly Line included.
    return max(voltage + VOLTAGE_TO_TIER, LV, min(built.get(m, NEVER) for m in machines))


def controllers(data):
    """Controller item(s) of each multiblock, matched by display name."""
    made = {out for r in data["recipes"] for out, _ in r[3]}
    by_name = defaultdict(list)
    for item, name in data["names"].items():
        if item in made:
            by_name[name].append(item)
    multiblocks = data["multiblocks"] | UNMARKED_MULTIBLOCKS
    return {m: by_name[CONTROLLER_NAMES.get(m, m)] for m in multiblocks}


def build_tiers(data):
    """First tier at which each multiblock can be built: the lowest tier whose recipes reach its controller from
    gathered items. Raising the tier, or building a multiblock, admits more recipes, so this is one reachability
    worklist that grows until nothing new turns up. Conservative: unknown items (no recipe) don't count as
    available, and a multiblock nobody can build goes to MAX, so the full view still has its recipes."""
    recipes, multiblocks = data["recipes"], data["multiblocks"]
    owner = defaultdict(list)
    for m, items in controllers(data).items():
        if not items:
            print(f"no controller with a recipe for {m}", file=sys.stderr)
        for item in items:
            owner[item].append(m)
    built, reached, used_by = {}, set(), defaultdict(list)
    missing = [None] * len(recipes)  # input slots not reached yet, once the recipe is admitted
    queue = [item for item in set(data["kinds"]) | set(data["names"]) if GATHERED.search(item)]
    pending = range(len(recipes))
    for tier in range(len(TIERS)):
        while True:
            later = []
            for idx in pending:
                if recipe_tier(recipes[idx], multiblocks, built) > tier:
                    later.append(idx)
                    continue
                slots = [set(ids) for ids, _ in recipes[idx][2] if reached.isdisjoint(ids)]
                missing[idx] = slots
                for slot in slots:
                    for item in slot:
                        used_by[item].append(idx)
                if not slots:
                    queue.extend(out for out, _ in recipes[idx][3])
            pending = later
            newly = set()
            while queue:
                item = queue.pop()
                if item in reached:
                    continue
                reached.add(item)
                newly.update(m for m in owner[item] if m not in built)
                for idx in used_by.pop(item, ()):
                    slots = missing[idx]
                    if not slots:
                        continue
                    slots[:] = [s for s in slots if item not in s]
                    if not slots:
                        queue.extend(out for out, _ in recipes[idx][3])
            if not newly:
                break
            built.update(dict.fromkeys(newly, tier))
    for m in set(multiblocks) | UNMARKED_MULTIBLOCKS:
        built.setdefault(m, len(TIERS) - 1)
    return built


# A cost is a pair (unknown, real): how many unknown items (no recipe, not gathered) a route needs, and
# everything else. Pairs compare lexicographically, so a route needing even a tiny amount of an unknown item
# never beats a fully known one: 5e-5 Oil Comb at a flat 1000 used to win the LV circuit's oil chain.
NO_ROUTE = (INF, INF)


def shown(c):
    """Single number for display: each unknown item counts as UNKNOWN, like before costs became pairs."""
    return c[0] * UNKNOWN + c[1]


def cheaper(a, b):
    """a < b, ignoring float noise so that sweeps don't flip between equal routes."""
    if a[0] != b[0] and not math.isclose(a[0], b[0], rel_tol=1e-6):
        return a[0] < b[0]
    return a[1] < b[1] * (1 - 1e-6)


def raw_cost(data, item, realistic):
    if realistic and item in REAL_FLUIDS:
        return REAL_FLUIDS[item] / FLUID_UNIT
    return data["ores"].get(data["names"].get(item), 1.0) / unit(data["kinds"], item)


def overhead(recipe, realistic):
    """What one run of the recipe costs on top of its inputs."""
    machine, eu, _, _, _, _, ticks = recipe[:7]
    if not realistic:
        return STEP + eu * EU_WEIGHT + MAGIC.get(machine, 0.0)
    if machine in MAGIC:
        run = MAGIC_RUN + MAGIC[machine]
    elif machine in STANDARD_MAPS:
        run = STANDARD_RUN
    elif machine in UNUSUAL_MAPS:
        run = UNUSUAL_RUN
    else:
        run = EXOTIC_RUN
    return run + eu * REAL_EU_WEIGHT + ticks / TICKS_PER_SECOND * REAL_SECOND_WEIGHT


def solve(data, max_tier=len(TIERS), realistic=False):
    """Cost of every item, and how it is made: "raw", or (recipe index, chosen item for each input slot)."""
    recipes, kinds = data["recipes"], data["kinds"]
    built = cached(data, "build", build_tiers)
    allowed = [recipe_tier(r, data["multiblocks"], built) <= max_tier for r in recipes]
    extra = [overhead(r, realistic) for r in recipes]
    producers = defaultdict(list)
    used_by = defaultdict(list)
    for idx, r in enumerate(recipes):
        if not allowed[idx]:
            continue
        for out, _ in r[3]:
            producers[out].append(idx)
        for slot_ids, _ in r[2]:
            for item in slot_ids:
                used_by[item].append(idx)

    cost, choice, done = {}, {}, set()
    waiting = [len(r[2]) if ok else -1 for r, ok in zip(recipes, allowed)]
    slot_done = [[False] * len(r[2]) for r in recipes]
    heap = []

    def offer(item, value, how):
        if item in done or not value < cost.get(item, NO_ROUTE):
            return
        cost[item], choice[item] = value, how
        heapq.heappush(heap, (value, item))

    made_somewhere = {out for r in recipes for out, _ in r[3]}
    for item in set(kinds) | set(producers):
        if GATHERED.search(item):
            offer(item, (0.0, raw_cost(data, item, realistic)), "raw")
        elif item not in made_somewhere:
            # Only for items no recipe makes at any tier. An item made only at a higher tier used to be "unknown"
            # here too, and at Steam an Extractor chain split one Octuple Compressed Cobblestone (only the LV
            # Implosion Compressor makes it) into 9^7 Compressed Cobblestone, showing up as "0 Octuple (?)".
            offer(item, (1.0 / unit(kinds, item), 0.0), "raw")

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
                picks, outs = outputs_cost(recipes[idx], extra[idx], cost)
                for out, value in outs:
                    offer(out, value, (idx, picks))

    # 2) Knuth vale solo se un prodotto costa più dei suoi ingredienti; in GT no (1 minerale -> 3 polveri),
    #    quindi qualcosa è stato chiuso troppo presto. Passate di rilassamento, accettando un ribasso
    #    solo se la ricetta non dipende (tramite le scelte attuali) dall'oggetto stesso: niente cicli.
    for _ in range(SWEEPS):
        changed = 0
        for idx, r in enumerate(recipes):
            if not allowed[idx]:
                continue
            picks, outs = outputs_cost(r, extra[idx], cost)
            for out, value in outs:
                if cheaper(value, cost.get(out, NO_ROUTE)) and not depends_on(choice, picks, out):
                    cost[out], choice[out] = value, (idx, picks)
                    changed += 1
        if not changed:
            break
    break_cycles(recipes, extra, producers, kinds, cost, choice)
    return cost, choice


def cheapest(ids, cost):
    return min(ids, key=lambda i: cost.get(i, NO_ROUTE))


def outputs_cost(recipe, extra, cost):
    """Cheapest item for each input slot, and the cost of each output when made from those."""
    inputs, outputs = recipe[2:4]
    picks = tuple(cheapest(ids, cost) for ids, _ in inputs)
    unknown, real = 0.0, extra
    for item, (_, amount) in zip(picks, inputs):
        u, c = cost.get(item, NO_ROUTE)
        unknown += amount * u
        real += amount * c
    if not (unknown < INF and real < INF):  # also catches 0 × INF = nan
        return picks, []
    return picks, [(item, (unknown / amount, real / amount)) for item, amount in outputs if amount > 0]


def depends_on(choice, picks, target):
    # The picks are frozen in each choice. Following "cheapest input right now" instead used to miss loops:
    # a later price drop changed which item filled a slot and closed Wood Plank <- Wood Pulp <- Oak Sign <-
    # Stick <- Wood Plank, which the tree then showed as an unknown "Wood Plank (?)".
    stack, seen = list(picks), set()
    while stack:
        item = stack.pop()
        if item == target:
            return True
        how = choice.get(item)
        if item in seen or how is None or how == "raw":
            continue
        seen.add(item)
        stack.extend(how[1])
    return False


def find_cycle(choice):
    """An item whose chosen recipe leads back to itself, or None."""
    state = {}  # 1 = on the current DFS path, 2 = finished
    for root in choice:
        if root in state:
            continue
        stack = [(root, iter(inputs_of(choice, root)))]
        state[root] = 1
        while stack:
            item, rest = stack[-1]
            nxt = next(rest, None)
            if nxt is None:
                state[item] = 2
                stack.pop()
            elif state.get(nxt) == 1:
                return nxt
            elif nxt not in state:
                state[nxt] = 1
                stack.append((nxt, iter(inputs_of(choice, nxt))))
    return None


def inputs_of(choice, item):
    how = choice.get(item)
    return () if how is None or how == "raw" else how[1]


def break_cycles(recipes, extra, producers, kinds, cost, choice):
    """Safety net: frozen picks should keep choices acyclic, but if a loop shows up, re-choose one of its items
    among recipes that don't depend on it. Approximation: items already priced through it keep their old cost."""
    while (item := find_cycle(choice)) is not None:
        best, how = (1.0 / unit(kinds, item), 0.0), "raw"
        for idx in producers[item]:
            picks, outs = outputs_cost(recipes[idx], extra[idx], cost)
            for out, value in outs:
                if out == item and value < best and not depends_on(choice, picks, item):
                    best, how = value, (idx, picks)
        cost[item], choice[item] = best, how
        print(f"loop through {item} rebuilt", file=sys.stderr)


def expand(data, cost, choice, item, amount, raw, steps, path=()):
    how = choice.get(item)
    if how is None or how == "raw" or item in path:
        raw[item] += amount
        return
    idx, picks = how
    machine, _, inputs, outputs = data["recipes"][idx][:4]
    made = next(a for o, a in outputs if o == item)
    runs = amount / made
    steps[(machine, item)] += runs
    for best, (_, need) in zip(picks, inputs):
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
    print(f"{amount:g} × {names.get(item, item)}  [{item}]  costo {shown(cost[item]) * amount:.2f}")
    print("\nmaterie prime:")
    shown_raw = [(r, a) for r, a in raw.items() if a >= TRACE * amount]
    for r, a in sorted(shown_raw, key=lambda kv: -kv[1] * shown(cost.get(kv[0], (0.0, 1.0)))):
        if kinds.get(r) == "fluid":
            label = "<1 L" if a < 0.5 else f"{a:.0f} L"
        else:
            label = "<0.01" if a < 0.005 else f"{a:.2f}".rstrip("0").rstrip(".")
        unknown = "" if GATHERED.search(r) else "  (?) nessuna ricetta: da trovare/comprare"
        print(f"  {label:>10}  {names.get(r, r)}{unknown}")
    print(f"\npassi ({len(steps)} ricette diverse):")
    for (machine, out), runs in sorted(steps.items(), key=lambda kv: kv[0][0]):
        print(f"  {runs:8.2f} × {machine}: {names.get(out, out)}")


def cached(data, name, compute):
    path = f"{DATA[:-4]}-{name}.cache.pkl"
    stamp = (os.path.getmtime(DATA), os.path.getmtime(__file__))
    if os.path.exists(path):
        hit = pickle.load(open(path, "rb"))
        if hit["stamp"] == stamp:
            return hit["value"]
    value = compute(data)
    pickle.dump({"stamp": stamp, "value": value}, open(path, "wb"))
    return value


def cached_solve(data, max_tier, realistic=False):
    name = ("real-" if realistic else "") + TIERS[min(max_tier, len(TIERS) - 1)]
    return cached(data, name, lambda d: solve(d, max_tier, realistic))


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
    realistic = "--real" in argv
    argv = [a for a in argv if a != "--real"]
    cost, choice = cached_solve(data, max_tier, realistic)
    amount = float(argv[1]) if len(argv) > 1 else 1.0
    item = pick(data, cost, argv[0])
    if item is None:
        print(f"non trovo (o non so fare) '{argv[0]}'")
        return 1
    show(data, cost, choice, item, amount)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
