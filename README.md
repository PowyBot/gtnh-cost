# gtnh-cost

Quanto costa *davvero* un oggetto di GregTech: New Horizons, in materie prime.

**Sul web: https://gtnh-cost.test.enn3.ovh** — cerca l'oggetto, scegli tier e quantità, apri l'albero delle ricette.
"Fermati a: lingotti e polveri" chiude l'albero ai lingotti e alle polveri semplici (`Copper Ingot`, `Copper Dust`;
non le pile, le impure/purified né i lingotti caldi), per vedere il conto in metalli invece che in minerali (`&stop=base`).
Sotto il titolo, "Costo per tier": i tier in cui l'oggetto diventa più economico (es. LV Machine Hull: LV 7.99 → HV 7.48
→ EV 6.00), per vedere se salire di tier conviene; tocca un tier per aprirlo. Il link è condivisibile, es. [LV Machine Hull a LV](https://gtnh-cost.test.enn3.ovh/?item=gregtech%3Agt.blockmachines%4011&tier=LV&n=1).

```
$ python3 cost.py "LV Machine Hull" --tier LV
1 × LV Machine Hull  costo 7.99
materie prime:
  4.88  Coal Ore
  0.67  Sticky Resin
  0.31  Redstone Ore
  0.12  Cassiterite Ore
  ...
passi (30 ricette diverse): ...
```

- `python3 cost.py "<nome>" [quantità] [--tier Stone|Steam|ULV|LV|MV|...] [--real]` — albero di ricette più economico fino alle
  materie prime. `--tier` usa solo ricette fattibili fino a quel tier (vedi [Tier](#tier)); `--real` sceglie quelle che
  userebbe un giocatore (vedi [Modalità realistica](#modalità-realistica)).
- `python3 cost.py --find hull` — cerca per nome.
- `python3 web/export.py /srv/test/gtnh-cost` — sito statico: per ogni tier (Stone..MAX) la ricetta scelta per ogni
  oggetto in `data/<tier>.json` (+ `.gz`; `real-<tier>.json` per la modalità realistica), nomi in `data/items.json`,
  costo per tier in `data/curves.json`; il browser rifà l'espansione di `cost.py`.
  Niente server: Caddy serve i file (`file_server { precompressed gzip }`). Ci mette qualche minuto (un solve per tier).
- `python3 build.py` — ricompatta il dataset (export oracle GTNH 2.9.0-rc-2, 280k ricette tra GregTech, crafting,
  fornace e Thaumcraft) in `recipes.pkl`, leggendolo una riga alla volta.

## Diagramma

Sotto il titolo, la catena come diagramma di flusso (Sankey a strati, `web/flow.js`, SVG senza librerie): materie
prime a sinistra, l'oggetto a destra, ogni banda larga quanto la quantità che passa (1000 L = 1; con
"Spessore: costo" invece quanto vale, `&weight=cost`). Le bande si stringono o si allargano apposta: in GT una ricetta
non conserva le quantità (1 minerale → 2 frantumati). Passa sopra un nodo per macchina, EU/t, durata e cicli;
cliccalo per chiuderlo o aprirlo (⊕ = chiuso). Da telefono: un tocco mostra i dettagli, il secondo apre o chiude.
Sopra i 45 nodi la catena parte chiusa dove diventa troppo profonda. Le scelte finiscono nell'URL (`&fold=`, `&open=`).
Colonne = cammino più lungo da una materia prima; l'ordine nelle colonne è un'euristica del baricentro (8 passate).

## Fabbrica

Sotto il risultato, "Fabbrica": scrivi quanti pezzi al minuto vuoi (`&rate=10`) e per ogni ricetta della catena
vedi quante macchine servono, i cicli al minuto, durata ed EU/t dopo l'overclock, gli EU/t medi; in fondo le materie
prime al minuto. Overclock GT5 al tier scelto: ogni tier sopra quello della ricetta (dal suo EU/t) dimezza il tempo
e quadruplica gli EU/t, fino a 1 tick. Non modellati: overclock perfetti (bobine dell'EBF), parallelismo dei
multiblocchi GT++, la fornace elettrica (le ricette di fornace senza EU contano come fornace classica, 10 s).
Il banco da lavoro è "a mano". Le macchine sono arrotondate per eccesso ricetta per ricetta; gli EU/t sono la media
a regime, non il picco.

## Tier

Ogni tier include quelli più bassi: Stone < Steam < ULV < LV < … < MAX. Una ricetta sta nel primo tier in cui c'è
una macchina che la sa fare (regole in `recipe_tier`, `cost.py`):

- **Stone**: banco da lavoro (shaped/shapeless), fornace, calderone, Coke Oven, Bricked Blast Furnace.
- **Steam**: le macchine a vapore di GT, bronze e steel (high pressure): Macerator, Compressor, Extractor,
  Forge Hammer, Alloy Smelter, Furnace; i multiblocchi a vapore di GT++: Steam Grinder, Squasher, Separator, Presser,
  Purifier, Blender, Fuser, Hearth. Solo ricette fino a 32 EU/t: le macchine a vapore cercano le ricette a voltaggio
  LV (`MTEBasicMachineBronze.checkRecipe` in GT5-Unofficial). Anche Thaumcraft sta qui (scelta a occhio: non ha tier GT).
- **ULV**: ricette fino a 8 EU/t, ma solo su macchine a blocco singolo. I multiblocchi si riconoscono dai
  `machineHandlers` dell'export; quelli senza (Chemical Plant, Nuclear Fission, HTGR, LFTR, Nanochip Conversion
  Complex, Component Assembly Line, Bacterial Vat, …) sono elencati a mano in `UNMARKED_MULTIBLOCKS`.
- **LV e oltre**: il `minimumTier` della ricetta nell'export, cioè il suo EU/t. Una macchina a blocco singolo si
  considera costruibile al tier del suo voltaggio. Un multiblocco invece sta almeno a LV e almeno al tier in cui si
  costruisce, che il dataset non dice: lo calcola `build_tiers`. È il tier più basso in cui le ricette ammesse
  arrivano al controller partendo da ciò che si raccoglie; ogni multiblocco costruito ammette nuove ricette, e si
  ripete finché non cambia più niente. Il controller si trova per nome (la mappa ricette si chiama come lui; le sei
  eccezioni sono in `CONTROLLER_NAMES`). È prudente: gli oggetti senza ricetta non contano come disponibili, quindi i
  multiblocchi il cui controller ne richiede uno (es. parti in Netherite: Fusion Mk-I, Spinmatron, Nanochip Assembly
  Complex, una ventina in tutto) finiscono a MAX. Esempi: Chemical Plant e Implosion Compressor a MV; Large Chemical
  Reactor, Distillation Tower e Vacuum Freezer a HV; Nuclear Fission (il reattore IC2) a EV; HTGR, LFTR e
  Assembly Line a IV; Component Assembly Line a UHV.

## Modello di costo

- Materie prime: minerali (costo = posto più comodo dove trovarli: overworld 1, ogni tier di razzo +3), roba raccolta
  (legno, sabbia, resina, drop dei mob), aria/acqua. 1000 L di fluido = 1 oggetto.
- Ricetta: somma input + energia (100k EU = 1) + un piccolo costo per passo; diviso per quanti pezzi produce.
  Input non consumati (stampi, circuiti programmati, attrezzi) non contano. I sottoprodotti sono gratis.
- Oggetti che nessuna ricetta produce e non si raccolgono: 1000 e marcati `(?)`. Un oggetto che si fa solo a un tier
  più alto invece è irraggiungibile, non sconosciuto. Le quantità sotto 1e-6 per pezzo non si mostrano.
- Thaumcraft (banco arcano, crogiolo, infusione): vis ed essentia non si stimano; la ricetta costa i suoi oggetti più una
  cifra fissa (0.5 / 1 / 4, `MAGIC` in `cost.py`).
- Fuori: macchine che creano materia (replicator, space mining, ...) o fanno energia, ricette senza input.

## Modalità realistica

"Più economico" non è "come lo fai davvero": a EV l'ossigeno per l'acciaio usciva dall'obsidiana del Boldarnator
(1 redstone → obsidiana → polvere → elettrolisi), e qua e là c'erano Thaumcraft e ricette di riciclo.
Con `--real` (sul sito: Ricette → realistiche, `&mode=real`) ogni ciclo di una ricetta costa, oltre agli input:

- energia: 50k EU = 1 (un minerale di carbone, macinato e bruciato in un generatore LV, rende più o meno tanto);
- tempo macchina: 100 s = 0.5, solo per spareggiare (in una base vera le macchine lavorano in parallelo);
- macchina: 0.05 se è standard (le macchine GT a blocco singolo, banco, fornace, EBF, Vacuum Freezer, LCR, Distillation
  Tower, Assembly Line…), 1 se è insolita (le copie GT++ come Multiblock Electrolyzer, Alloy Blast Smelter, Dehydrator…),
  5 se è esotica (tutto il resto: Boldarnator, Helioflux, …), 20 per Thaumcraft. Liste in `STANDARD_MAPS` e `UNUSUAL_MAPS`.

Acqua e aria costano quasi niente (0.05 ogni 1000 L: una pompa, un gas collector), ossigeno e azoto 0.2 (dall'aria
in centrifuga): in modalità economica valgono 1 come ogni cosa raccolta, ed era questo a far vincere l'obsidiana.
Il numero che esce è un punteggio, non più materie prime: per le quantità guarda la tabella.

Risultato (`python3 cost.py "LV Machine Hull" --tier EV --real`): niente Boldarnator, Thaumcraft, Alloy Blast Smelter
né Multiblock Electrolyzer; acciaio nell'EBF con l'ossigeno dall'aria, 24 macchine diverse invece di 33. Lo stesso per
HV Hull, Electronic Circuit, Good Electronic Circuit e Microprocessor: solo macchine standard (a EV l'HV Hull usa
ancora l'Alloy Blast Smelter, che a quel punto molti hanno davvero).

Approssimazione: la penalità è per ciclo, non per macchina costruita. Un vero "costo per macchina distinta nella catena"
non è additivo (dipende da tutta la catena) e il Dijkstra ha bisogno di costi additivi. Così un ingrediente usato in
tracce può ancora passare da una macchina strana, perché la sua penalità si moltiplica per una quantità piccola.

## Algoritmo

Dijkstra generalizzato di Knuth sugli iperarchi (una ricetta scatta quando tutti gli input hanno costo definitivo),
poi passate di rilassamento: in GT un prodotto può costare meno di un ingrediente (1 minerale → 3 polveri),
cosa che rompe l'ipotesi di Knuth. Un ribasso si accetta solo se non crea cicli nelle scelte.
Un label-correcting puro ci metteva 2 minuti e trovava cicli "moltiplicatori"; così sono ~10 s (poi in cache).

Limiti noti: "più economico" non è "come lo fai davvero" (a volte sceglie strade bizzarre ma lecite: per questo c'è
la modalità realistica); non sa nulla di parallelismo o di macchine già costruite.
