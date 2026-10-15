# gtnh-cost

Quanto costa *davvero* un oggetto di GregTech: New Horizons, in materie prime.

**Sul web: https://gtnh-cost.test.enn3.ovh** — cerca l'oggetto, scegli tier e quantità, apri l'albero delle ricette.
Il link è condivisibile, es. [LV Machine Hull a LV](https://gtnh-cost.test.enn3.ovh/?item=gregtech%3Agt.blockmachines%4011&tier=LV&n=1).

```
$ python3 cost.py "LV Machine Hull" --tier LV
1 × LV Machine Hull  costo 8.49
materie prime:
  4.05  Coal Ore
  2.48  Iron Ore
  0.67  Sticky Resin
  0.12  Cassiterite Ore
  ...
passi (33 ricette diverse): ...
```

- `python3 cost.py "<nome>" [quantità] [--tier LV|MV|HV|...]` — albero di ricette più economico fino alle materie prime.
  `--tier` usa solo ricette fattibili fino a quel voltaggio.
- `python3 cost.py --find hull` — cerca per nome.
- `python3 web/export.py /srv/test/gtnh-cost` — sito statico: per ogni tier (ULV..MAX) la ricetta scelta per ogni
  oggetto in `data/<tier>.json` (+ `.gz`), nomi in `data/items.json`; il browser rifà l'espansione di `cost.py`.
  Niente server: Caddy serve i file (`file_server { precompressed gzip }`). Ci mette qualche minuto (un solve per tier).
- `python3 build.py` — ricompatta il dataset (export oracle GTNH 2.9.0-rc-2, 280k ricette tra GregTech, crafting,
  fornace e Thaumcraft) in `recipes.pkl`, leggendolo una riga alla volta.

## Modello di costo

- Materie prime: minerali (costo = posto più comodo dove trovarli: overworld 1, ogni tier di razzo +3), roba raccolta
  (legno, sabbia, resina, drop dei mob), aria/acqua. 1000 L di fluido = 1 oggetto.
- Ricetta: somma input + energia (100k EU = 1) + un piccolo costo per passo; diviso per quanti pezzi produce.
  Input non consumati (stampi, circuiti programmati, attrezzi) non contano. I sottoprodotti sono gratis.
- Oggetti che nessuna ricetta produce e non si raccolgono: 1000 e marcati `(?)`.
- Thaumcraft (banco arcano, crogiolo, infusione): vis ed essentia non si stimano; la ricetta costa i suoi oggetti più una
  cifra fissa (0.5 / 1 / 4, `MAGIC` in `cost.py`).
- Fuori: macchine che creano materia (replicator, space mining, ...) o fanno energia, ricette senza input.

## Algoritmo

Dijkstra generalizzato di Knuth sugli iperarchi (una ricetta scatta quando tutti gli input hanno costo definitivo),
poi passate di rilassamento: in GT un prodotto può costare meno di un ingrediente (1 minerale → 3 polveri),
cosa che rompe l'ipotesi di Knuth. Un ribasso si accetta solo se non crea cicli nelle scelte.
Un label-correcting puro ci metteva 2 minuti e trovava cicli "moltiplicatori"; così sono ~10 s (poi in cache).

Limiti noti: "più economico" non è "come lo fai davvero" (a volte sceglie strade bizzarre ma lecite);
non sa nulla di parallelismo, tempi o macchine già costruite.
