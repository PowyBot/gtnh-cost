"""Compatta recipes.json.gz (253k ricette) in un pickle leggero per cost.py."""
import gzip
import json
import pickle
import sys

DATASET = "/home/enn3/gtnh-export/datasets/2.9.0-rc-2-enn3/recipes.json.gz"
OUT = "/home/enn3/projects/gtnh-cost/recipes.pkl"

# Macchine che creano materia dal nulla, la consumano per energia o sono solo informative:
# terrebbero il costo di qualcosa a zero o non sono "fare un oggetto".
SKIP_MACHINES = {
    "Extreme Entity Crusher", "Space Mining", "Replicator", "Matter Fabricator", "Mass Fabrication",
    "Matter Amplifier", "Research Station", "Scanner", "Tank", "Eye of Harmony", "Godforge Upgrades",
    "Zhuhai Fishing Port", "Acid Generator", "Thermal Boiler", "Large Boiler", "Industrial Chisel",
    "Tree Growth Simulator", "Rock Breaker", "Printer", "Crop Gene Extractor", "Crop Synthesizer",
    "Crop Breeder", "Magic Energy Absorber Fuels", "Combustion Generator Fuels", "Plasma Generator Fuels",
    "Bee Produce", "IC2 Crop", "Ore Vein", "Small Ore", "Underground Fluid", "Solar Tower",
    "Thaumcraft Crucible", "Thaumcraft Infusion", "Thaumcraft Arcane Crafting", "Thaumcraft",
    "Isotope Decay", "Molecular Transformer",
}
SKIP_WORDS = ("Naquadah Reactor", "Generator", "Fuels")


TIERS = ["NONE", "ULV", "LV", "MV", "HV", "EV", "IV", "LuV", "ZPM", "UV", "UHV", "UEV", "UIV", "UMV", "UXV", "OpV", "MAX"]
VARIANTS = {}  # "minecraft:wool" -> tutte le metadata, per gli input jolly "@32767"
OREDICT = {}  # "oredict:plateSteel" -> oggetti concreti accettati (dalle risorse del dataset)


def slot(entry):
    ids = [entry["id"]] + [a["id"] for a in entry.get("alternatives", ())]
    ids += [alt for i in ids for alt in OREDICT.get(i, ())]
    ids += [alt for i in ids if i.endswith("@32767") for alt in VARIANTS.get(i[:-6], ())]
    return tuple(dict.fromkeys(ids)), float(entry["amount"])


def consumed(entry):
    # attrezzi da crafting e catalizzatori non si consumano; gli aspetti di Thaumcraft non li contiamo
    return entry.get("consumed", True) and entry["kind"] != "aspect" and not entry["id"].startswith("oredict:craftingTool")


def keep(recipe):
    machine = recipe.get("machineType") or ""
    if machine in SKIP_MACHINES:
        return False
    return not any(w in machine for w in SKIP_WORDS)


def compact(recipe):
    inputs = [slot(i) for i in recipe["inputs"] if consumed(i)]
    outputs = [(o["id"], o["amount"] * o.get("chance", 1.0)) for o in recipe["outputs"] if o["kind"] != "aspect"]
    eu = max(recipe.get("eut") or 0, 0) * max(recipe.get("durationTicks") or 0, 0)
    tier = TIERS.index(recipe.get("minimumTier")) if recipe.get("minimumTier") in TIERS else 0
    return recipe["machineType"], eu, inputs, outputs, tier


def dimension_cost(dim):
    # tier del razzo per arrivarci: l'overworld costa 1, ogni tier di razzo +3, l'End sta a metà
    if dim["name"] in ("The End", "EndAsteroid"):
        return 2.0
    return 1.0 + 3.0 * dim["tier"]


def ore_costs(data):
    """Nome del minerale -> costo del posto più comodo dove trovarlo (vene GregTech)."""
    best = {}
    for r in data["recipes"]:
        if r["kind"] != "ore_vein":
            continue
        where = min((dimension_cost(d) for d in r["metadata"].get("dimensions", ())), default=None)
        for o in r["outputs"] if where is not None else ():
            best[o["displayName"]] = min(best.get(o["displayName"], where), where)
    return best


def main():
    data = json.load(gzip.open(DATASET))
    names = {r["id"]: r.get("displayName", r["id"]) for r in data["resources"]}
    kinds = {r["id"]: r["kind"] for r in data["resources"]}
    OREDICT.update({r["id"]: [a["id"] for a in r["alternatives"]] for r in data["resources"] if r.get("alternatives")})
    for r in data["recipes"]:
        for e in r["outputs"]:
            VARIANTS.setdefault(e["id"].split("@")[0], []).append(e["id"])
    recipes = [compact(r) for r in data["recipes"] if keep(r)]
    # senza input = materia dal nulla (o ricette fantasma dell'export): fuori
    recipes = [r for r in recipes if r[2] and r[3]]
    for r in data["recipes"]:
        for e in r["inputs"] + r["outputs"]:
            names.setdefault(e["id"], e.get("displayName", e["id"]))
            kinds.setdefault(e["id"], e["kind"])
    pickle.dump({"recipes": recipes, "names": names, "kinds": kinds, "ores": ore_costs(data)}, open(OUT, "wb"))
    print(f"{len(recipes)} ricette tenute su {len(data['recipes'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
