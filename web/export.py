"""Precalcola il sito statico: per ogni tier la ricetta scelta per ogni oggetto, più i nomi per la ricerca.

uso: python3 web/export.py /srv/test/gtnh-cost
Il browser fa poi la stessa espansione di cost.py (expand) sui file JSON.
data/curves.json: per ogni oggetto, i tier in cui diventa più economico ([tier, costo], ...).
"""
import gzip
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


def write(path, obj):
    text = json.dumps(obj, separators=(",", ":"))
    open(path, "w").write(text)
    with gzip.open(path + ".gz", "wt", compresslevel=9) as f:
        f.write(text)


def main(out):
    data = gc.load()
    names, kinds, recipes = data["names"], data["kinds"], data["recipes"]
    ids = sorted(set(names) | set(kinds))
    index = {item: n for n, item in enumerate(ids)}
    os.makedirs(f"{out}/data", exist_ok=True)
    # [id, nome, fluido?, si raccoglie?]
    write(f"{out}/data/items.json", [[i, names.get(i, i), int(kinds.get(i) == "fluid"), int(bool(gc.GATHERED.search(i)))]
                                     for i in ids])
    curves = [[] for _ in ids]
    for tier in gc.TIERS:
        cost, choice = gc.cached_solve(data, gc.TIERS.index(tier))
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
        write(f"{out}/data/{tier}.json", {"machines": machines, "cost": costs, "how": how})
        t = gc.TIERS.index(tier)
        for curve, c, item in zip(curves, costs, ids):
            # a cost with unknown items in it is a flat 1000 each, not a price worth comparing across tiers
            if cost.get(item, gc.NO_ROUTE)[0] == 0 and (not curve or c < curve[-1][1] * (1 - CURVE_STEP)):
                curve.append([t, float(f"{c:.5g}")])
        print(tier, len(how), file=sys.stderr)
    write(f"{out}/data/curves.json", curves)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("index.html", "app.js", "style.css"):
        shutil.copy(f"{here}/{name}", f"{out}/{name}")


if __name__ == "__main__":
    main(sys.argv[1])
