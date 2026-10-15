"""Precalcola il sito statico: per ogni tier la ricetta scelta per ogni oggetto, più i nomi per la ricerca.

uso: python3 web/export.py /srv/test/gtnh-cost
Il browser fa poi la stessa espansione di cost.py (expand) sui file JSON.
"""
import gzip
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cost as gc  # noqa: E402



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
    for tier in gc.TIERS:
        cost, choice = gc.cached_solve(data, gc.TIERS.index(tier))
        machines, how = [], {}
        for item, idx in choice.items():
            if idx == "raw" or item not in index:
                continue
            machine, _, inputs, outputs, _, eut, ticks = recipes[idx][:7]
            if machine not in machines:
                machines.append(machine)
            made = next(a for o, a in outputs if o == item)
            flat = [x for ids_, need in inputs for x in (index[gc.cheapest(ids_, cost)], need)]
            how[index[item]] = [machines.index(machine), eut, ticks, made, flat]
        costs = [float(f"{cost[i]:.12g}") if cost.get(i, gc.INF) < gc.INF else None for i in ids]
        write(f"{out}/data/{tier}.json", {"machines": machines, "cost": costs, "how": how})
        print(tier, len(how), file=sys.stderr)
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("index.html", "app.js", "style.css"):
        shutil.copy(f"{here}/{name}", f"{out}/{name}")


if __name__ == "__main__":
    main(sys.argv[1])
