"""Precalcola il sito statico: per ogni tier la ricetta scelta per ogni oggetto, più i nomi per la ricerca.

uso: python3 web/export.py /srv/test/gtnh-cost
Il browser fa poi la stessa espansione di cost.py (expand) sui file JSON.
data/curves.json: per ogni oggetto, i tier in cui diventa più economico ([tier, costo], ...).
data/alt-<tier>.json: per ogni oggetto le ricette scartate più economiche, per "perché questa ricetta?".
Ogni file esiste due volte: <tier>.json è la strada più economica, real-<tier>.json quella realistica (cost.py --real).
"""
import gzip
import heapq
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cost as gc  # noqa: E402

# "Cost per tier" keeps a tier only where the item gets this much cheaper, so the file stays small and the
# line shows the tiers worth reaching, not float noise from re-solving. Stored with 5 digits: the tier files
# have the exact costs.
CURVE_STEP = 0.02
# "Why this recipe?" lists this many discarded recipes per item, each with at most ALT_INPUTS inputs: enough to
# see the runner-up, and the alternative files stay around 1 MB gzipped per tier.
ALTERNATIVES, ALT_INPUTS = 3, 4


def write(path, obj):
    text = json.dumps(obj, separators=(",", ":"))
    open(path, "w").write(text)
    with gzip.open(path + ".gz", "wt", compresslevel=9) as f:
        f.write(text)


def main(out):
    data = gc.load()
    names, kinds = data["names"], data["kinds"]
    ids = sorted(set(names) | set(kinds))
    index = {item: n for n, item in enumerate(ids)}
    os.makedirs(f"{out}/data", exist_ok=True)
    # [id, nome, fluido?, si raccoglie?]
    write(f"{out}/data/items.json", [[i, names.get(i, i), int(kinds.get(i) == "fluid"), int(bool(gc.GATHERED.search(i)))]
                                     for i in ids])
    for prefix, realistic in (("", False), ("real-", True)):
        export_mode(out, data, ids, index, prefix, realistic)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("index.html", "app.js", "flow.js", "style.css"):
        shutil.copy(f"{here}/{name}", f"{out}/{name}")


def export_mode(out, data, ids, index, prefix, realistic):
    recipes = data["recipes"]
    built = gc.cached(data, "build", gc.build_tiers)
    tiers = [gc.recipe_tier(r, data["multiblocks"], built) for r in recipes]
    extra = [gc.overhead(r, realistic) for r in recipes]
    curves = [[] for _ in ids]
    for tier in gc.TIERS:
        cost, choice = gc.cached_solve(data, gc.TIERS.index(tier), realistic)
        allowed = [t <= gc.TIERS.index(tier) for t in tiers]
        write(f"{out}/data/alt-{prefix}{tier}.json", alternatives(recipes, allowed, extra, cost, choice, index))
        machines, how = [], {}
        for item, chosen in choice.items():
            if chosen == "raw" or item not in index:
                continue
            idx, picks = chosen
            machine, _, inputs, outputs, _, eut, ticks = recipes[idx][:7]
            if machine not in machines:
                machines.append(machine)
            made = next(a for o, a in outputs if o == item)
            flat = [x for best, (_, need) in zip(picks, inputs) for x in (index[best], need)]
            how[index[item]] = [machines.index(machine), eut, ticks, made, flat]
        shown = [gc.shown(cost.get(i, gc.NO_ROUTE)) for i in ids]
        costs = [float(f"{c:.12g}") if c < gc.INF else None for c in shown]
        write(f"{out}/data/{prefix}{tier}.json", {"machines": machines, "cost": costs, "how": how})
        t = gc.TIERS.index(tier)
        for curve, c, item in zip(curves, costs, ids):
            # a cost with unknown items in it is a flat 1000 each, not a price worth comparing across tiers
            if cost.get(item, gc.NO_ROUTE)[0] == 0 and (not curve or c < curve[-1][1] * (1 - CURVE_STEP)):
                curve.append([t, float(f"{c:.5g}")])
        print(prefix + tier, len(how), file=sys.stderr)
    write(f"{out}/data/{prefix}curves.json", curves)


def alternatives(recipes, allowed, extra, cost, choice, index):
    """For every item, the cheapest recipes the solver did not choose, priced with the final costs:
    [machine, cost of one item, made, [input, amount, ...]]. Raw items get them too (why oxygen from the air?)."""
    found = {}
    for idx, r in enumerate(recipes):
        if not allowed[idx]:
            continue
        picks, outs = gc.outputs_cost(r, extra[idx], cost)
        for item, value in outs:
            how = choice.get(item)
            if item not in index or how is None or how != "raw" and how[0] == idx:
                continue
            heap = found.setdefault(item, [])
            # keep a few spares: oredict variants make the same recipe several times
            entry = (-gc.shown(value), idx, picks)
            if len(heap) < 4 * ALTERNATIVES:
                heapq.heappush(heap, entry)
            elif entry > heap[0]:
                heapq.heapreplace(heap, entry)
    machines, alt = [], {}
    for item, heap in found.items():
        rows, seen = [], set()
        for minus, idx, picks in sorted(heap, reverse=True):
            machine, _, inputs, outputs = recipes[idx][:4]
            key = (machine, picks)
            if key in seen:
                continue
            seen.add(key)
            if machine not in machines:
                machines.append(machine)
            made = next(a for o, a in outputs if o == item)
            flat = [x for best, (_, need) in list(zip(picks, inputs))[:ALT_INPUTS] for x in (index[best], need)]
            rows.append([machines.index(machine), float(f"{-minus:.6g}"), made, flat])
            if len(rows) == ALTERNATIVES:
                break
        alt[index[item]] = rows
    return {"machines": machines, "alt": alt}


if __name__ == "__main__":
    main(sys.argv[1])
