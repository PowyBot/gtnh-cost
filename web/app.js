"use strict";
// Stessa espansione di cost.py, sui file precalcolati da web/export.py.
const TIERS = ["Stone", "Steam", "ULV", "LV", "MV", "HV", "EV", "IV", "LuV", "ZPM", "UV", "UHV", "UEV", "UIV", "UMV", "UXV", "OpV", "MAX"];
const $ = (id) => document.getElementById(id);
let items = [], lower = [], byId = new Map(), files = new Map(), selected = null;
// "Stop at ingots & dusts": the tree ends at plain Copper Ingot / Copper Dust instead of ores. Piles, impure and
// purified dusts, and hot ingots are steps on the way there, so they still expand.
const BASE_MATERIAL = /^(?!Tiny Pile |Small Pile |Impure |Purified |Hot ).* (Ingot|Dust)$/;
let baseMaterials = new Set();
const stopsAt = (item, root) => !root && $("stop").value === "base" && baseMaterials.has(item);
// unknown = nobody gathers it and no recipe makes it at this tier; a leaf where the tree stopped on purpose has one
const unknown = (data, item) => !items[item][3] && !data.how[item];

// arrotonda come Python (valore binario esatto, pari a metà), così i numeri coincidono con la CLI
function pyFixed(a, d) {
  const exact = a.toFixed(100), dot = exact.indexOf(".");
  const head = exact.slice(0, d ? dot + 1 + d : dot), tail = exact.slice(dot + 1 + d);
  return /^50*$/.test(tail) && +head.at(-1) % 2 === 0 ? head : a.toFixed(d);
}
// a trace above TRACE still deserves a number other than 0
const fmt = (i, a) => items[i][2] ? (a < 0.5 ? "<1 L" : `${pyFixed(a, 0)} L`)
  : a < 0.005 ? "<0.01" : pyFixed(a, 2).replace(/0+$/, "").replace(/\.$/, "");
const TIER_LABELS = { Stone: "Stone (a mano, fornace)", Steam: "Steam (vapore)", MAX: "tutti (MAX)" };
const tierLabel = (t) => TIER_LABELS[t] || t;
const TRACE = 1e-6; // same as cost.py: raw amounts below this per item made are dust from long splitting chains

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

// "real-" files hold the realistic choices (cost.py --real), the others the cheapest ones
const prefix = () => $("mode").value === "real" ? "real-" : "";

function load(file) {
  if (!files.has(file)) files.set(file, getJSON(`data/${file}.json`).catch((e) => { files.delete(file); throw e; }));
  return files.get(file);
}
const loadTier = (t) => load(prefix() + t);
// [[tier, cost], ...] per item: the tiers where it gets cheaper. Loaded on the first result, not at start.
const loadCurves = () => load(prefix() + "curves");

async function showCurve(item, tier, n) {
  const curve = (await loadCurves())[item];
  if (item !== selected || curve.length < 2) { $("curve").hidden = true; return; }
  const at = TIERS.indexOf(tier);
  $("curve").replaceChildren($("mode").value === "real" ? "Punteggio per tier: " : "Costo per tier: ", ...curve.flatMap(([t, c], k) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = `${TIERS[t]} ${pyFixed(c * n, 2)}`;
    // the tier in use is the last step at or below the chosen one
    if (t <= at && (curve[k + 1]?.[0] ?? Infinity) > at) b.className = "now";
    b.addEventListener("click", () => { $("tier").value = TIERS[t]; submit().catch(fail); });
    return k ? [" → ", b] : [b];
  }));
  $("curve").hidden = false;
}

// Ricerca: frase intera > parole tutte presenti > lettere in ordine.
function search(q) {
  q = q.trim().toLowerCase();
  if (!q) return [];
  const words = q.split(/\s+/), hits = [];
  for (let i = 0; i < lower.length; i++) {
    const s = lower[i];
    let score;
    const at = s.indexOf(q);
    if (s === q) score = 0;
    else if (at === 0) score = 1;
    else if (at > 0) score = 2;
    else if (words.every((w) => s.includes(w))) score = 3;
    else {
      let k = 0;
      for (let j = 0; j < s.length && k < q.length; j++) if (s[j] === q[k]) k++;
      if (k < q.length) continue;
      score = 4;
    }
    hits.push([score, s.length, i]);
  }
  hits.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return hits.slice(0, 40).map((h) => h[2]);
}

function showSuggest(list) {
  const ul = $("suggest");
  ul.replaceChildren(...list.map((i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span></span> <small></small>`;
    li.firstChild.textContent = items[i][1];
    li.lastChild.textContent = items[i][0];
    li.onmousedown = (e) => { e.preventDefault(); choose(i); };
    return li;
  }));
  ul.hidden = !list.length;
}

function choose(i) {
  selected = i;
  $("q").value = items[i][1];
  $("suggest").hidden = true;
  submit().catch(fail);
}

function expand(data, item, amount, raw, steps, path) {
  const how = data.how[item];
  if (!how || path.has(item) || stopsAt(item, path.size === 0)) { raw.set(item, (raw.get(item) || 0) + amount); return; }
  const [machine, , , made, inputs] = how, runs = amount / made, key = `${machine} ${item}`;
  steps.set(key, [machine, item, (steps.get(key)?.[2] || 0) + runs]);
  path.add(item);
  for (let k = 0; k < inputs.length; k += 2) expand(data, inputs[k], inputs[k + 1] * runs, raw, steps, path);
  path.delete(item);
}

function node(data, item, amount, path) {
  const how = data.how[item], cyc = path.includes(item), stop = stopsAt(item, path.length === 0);
  const label = `<span class="amt">${fmt(item, amount)}</span> <span class="name"></span>`;
  if (!how || cyc || stop) {
    const div = document.createElement("div");
    div.className = "leaf";
    div.innerHTML = label + (unknown(data, item) ? ` <span class="warn">(?)</span>` : "");
    div.querySelector(".name").textContent = items[item][1];
    return div;
  }
  const [m, eut, ticks, made] = how, runs = amount / made;
  const d = document.createElement("details");
  d.innerHTML = `<summary>${label} <span class="how"></span></summary>`;
  d.querySelector(".name").textContent = items[item][1];
  d.querySelector(".how").textContent = [data.machines[m], eut ? `${eut.toLocaleString("it")} EU/t` : "", ticks > 1 ? `${+(ticks / 20).toFixed(2)} s` : "",
    `× ${+runs.toPrecision(3)}`].filter(Boolean).join(" · ");
  d.addEventListener("toggle", () => {
    if (!d.open || d.dataset.done) return;
    d.dataset.done = 1;
    const inputs = how[4], box = document.createElement("div");
    box.className = "kids";
    for (let k = 0; k < inputs.length; k += 2) box.append(node(data, inputs[k], inputs[k + 1] * runs, path.concat(item)));
    d.append(box);
  });
  return d;
}

// Factory planner: machines for a steady rate. GT5 overclock: each voltage tier above the recipe's halves the
// duration and quadruples the EU/t, down to 1 tick (perfect overclocks of EBF coils etc. are not modelled).
const VOLTAGE_BASE = 8; // ULV volts; each tier is ×4
const TICKS_PER_MINUTE = 1200;
const HAND = new Set(["Shaped Crafting", "Shapeless Crafting"]);
const recipeVoltage = (eut) => { let v = 0; while (VOLTAGE_BASE * 4 ** v < eut) v++; return v; };

function overclock(eut, ticks, tier) {
  const machine = TIERS.indexOf(tier) - TIERS.indexOf("ULV");
  if (!eut || machine < 0) return [eut, ticks]; // no power, or a steam/stone age machine
  let oc = machine - recipeVoltage(eut);
  while (oc-- > 0 && ticks >= 2) { ticks = Math.floor(ticks / 2); eut *= 4; }
  return [eut, ticks];
}

// One row per recipe of the chain for `rate` items a minute; steps come from expand() for one item.
function showPlan(data, raw, steps, tier) {
  const rate = Math.max(+$("rate").value || 0, 0);
  let machinesTotal = 0, euTotal = 0;
  const rows = [...steps.values()].map(([m, item, runs]) => {
    const [, eut, ticks] = data.how[item], perMinute = runs * rate, name = data.machines[m];
    const [ocEut, ocTicks] = overclock(eut, ticks, tier);
    // crafting is by hand (or an autocrafter), and a recipe with no duration in the export can't be sized
    const machines = HAND.has(name) || !ocTicks ? null : perMinute * ocTicks / TICKS_PER_MINUTE;
    const eu = machines === null ? 0 : machines * ocEut;
    if (machines !== null) { machinesTotal += Math.ceil(machines - 1e-9); euTotal += eu; }
    return { name, item, perMinute, machines, ocEut, ocTicks, eu };
  }).filter((r) => r.perMinute >= TRACE * rate).sort((a, b) => (b.machines ?? -1) - (a.machines ?? -1));
  $("plan").tBodies[0].replaceChildren(...rows.map((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num"></td><td></td><td class="num"></td>`;
    tr.cells[0].textContent = r.machines === null ? (HAND.has(r.name) ? "a mano" : "—") : `${Math.ceil(r.machines - 1e-9)}`;
    if (r.machines !== null) tr.cells[0].title = `${+r.machines.toPrecision(3)} macchine a pieno regime`;
    tr.cells[1].innerHTML = `<span></span> <span class="how"></span>`;
    tr.cells[1].firstChild.textContent = `${r.name}: ${items[r.item][1]}`;
    tr.cells[1].lastChild.textContent = [`${+r.perMinute.toPrecision(3)} cicli/min`, r.ocTicks ? `${+(r.ocTicks / 20).toFixed(2)} s` : "",
      r.ocEut ? `${r.ocEut.toLocaleString("it")} EU/t` : ""].filter(Boolean).join(" · ");
    tr.cells[2].textContent = r.eu ? Math.round(r.eu).toLocaleString("it") : "";
    return tr;
  }));
  const voltage = TIERS.indexOf(tier) - TIERS.indexOf("ULV"), amps = euTotal / (VOLTAGE_BASE * 4 ** voltage);
  $("plantotal").textContent = `${machinesTotal} macchine, ${Math.round(euTotal).toLocaleString("it")} EU/t in media` +
    (voltage >= 0 ? ` (${amps.toFixed(1)} A a ${tier})` : " (a vapore: le macchine vogliono vapore, circa 2 L per EU)");
  $("planraw").tBodies[0].replaceChildren(...[...raw].filter(([, a]) => a >= TRACE).sort((a, b) => b[1] - a[1]).map(([r, a]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num"></td><td></td>`;
    tr.cells[0].textContent = fmt(r, a * rate);
    tr.cells[1].textContent = items[r][1];
    return tr;
  }));
}

async function submit() {
  const tier = $("tier").value, n = Math.max(+$("n").value || 1, 1e-9);
  if (selected === null) {
    const hit = search($("q").value)[0];
    if (hit === undefined) { $("status").textContent = "Nessun oggetto con quel nome."; return; }
    selected = hit;
    $("q").value = items[hit][1];
  }
  const params = new URLSearchParams({ item: items[selected][0], tier, n });
  if (+$("rate").value !== 1) params.set("rate", $("rate").value);
  if ($("stop").value === "base") params.set("stop", "base");
  if ($("mode").value === "real") params.set("mode", "real");
  history.replaceState(null, "", `?${params}`);
  $("status").textContent = "Calcolo…";
  const data = await loadTier(tier), item = selected;
  if (data.cost[item] === null) { $("status").textContent = "Irraggiungibile."; $("result").hidden = true; return; }
  const raw = new Map(), steps = new Map();
  expand(data, item, n, raw, steps, new Set());
  const what = $("mode").value === "real" ? "punteggio realistico" : "costo";
  $("title").textContent = `${n} × ${items[item][1]} — tier ${tierLabel(tier)} — ${what} ${pyFixed(data.cost[item] * n, 2)}`;
  $("costhint").hidden = $("mode").value === "real";
  $("realhint").hidden = $("mode").value !== "real";
  $("rawtitle").textContent = $("stop").value === "base" ? "Lingotti, polveri e materie prime" : "Materie prime";
  $("raw").tBodies[0].replaceChildren(...[...raw].filter(([, a]) => a >= TRACE * n).sort((a, b) => b[1] * (data.cost[b[0]] ?? 1) - a[1] * (data.cost[a[0]] ?? 1)).map(([r, a]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num"></td><td></td>`;
    tr.cells[0].textContent = fmt(r, a);
    tr.cells[1].textContent = items[r][1] + (unknown(data, r) ? " (?) nessuna ricetta: da trovare/comprare" : "");
    if (unknown(data, r)) tr.className = "warn";
    return tr;
  }));
  $("steps").tBodies[0].replaceChildren(...[...steps.values()].sort((a, b) => data.machines[a[0]].localeCompare(data.machines[b[0]])).map(([m, out, runs]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num"></td><td></td>`;
    tr.cells[0].textContent = `${runs.toFixed(2)} ×`;
    tr.cells[1].textContent = `${data.machines[m]}: ${items[out][1]}`;
    return tr;
  }));
  $("stepsbox").querySelector("summary").textContent = `Tutti i passi (${steps.size} ricette diverse)`;
  const perItem = new Map(), perItemSteps = new Map();
  expand(data, item, 1, perItem, perItemSteps, new Set());
  showPlan(data, perItem, perItemSteps, tier);
  const root = node(data, item, n, []);
  if (root.tagName === "DETAILS") root.open = true;
  $("tree").replaceChildren(root);
  $("result").hidden = false;
  $("status").textContent = "";
  showCurve(item, tier, n).catch(() => { $("curve").hidden = true; });
}

async function init() {
  $("tier").innerHTML = TIERS.map((t) => `<option value="${t}">${tierLabel(t)}</option>`).join("");
  const p = new URLSearchParams(location.search);
  $("tier").value = TIERS.includes(p.get("tier")) ? p.get("tier") : "LV";
  if (p.get("n")) $("n").value = p.get("n");
  if (p.get("stop") === "base") $("stop").value = "base";
  if (p.get("mode") === "real") $("mode").value = "real";
  if (p.get("rate")) $("rate").value = p.get("rate");
  items = await getJSON("data/items.json");
  lower = items.map((x) => x[1].toLowerCase());
  items.forEach((x, i) => byId.set(x[0], i));
  baseMaterials = new Set(items.flatMap((x, i) => BASE_MATERIAL.test(x[1]) ? [i] : []));
  $("q").disabled = false;
  $("status").textContent = "";
  $("q").addEventListener("input", () => { selected = null; showSuggest(search($("q").value)); });
  $("q").addEventListener("blur", () => { $("suggest").hidden = true; });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("suggest").hidden = true;
  });
  $("form").addEventListener("submit", (e) => { e.preventDefault(); $("suggest").hidden = true; submit().catch(fail); });
  $("rate").addEventListener("input", () => { if (!$("result").hidden) submit().catch(fail); });
  for (const id of ["tier", "stop", "mode"]) $(id).addEventListener("change", () => { if (!$("result").hidden) submit().catch(fail); });
  $("share").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(location.href); $("share").textContent = "Copiato!"; }
    catch { prompt("Link:", location.href); }
  });
  if (byId.has(p.get("item"))) choose(byId.get(p.get("item")));
}

function fail(e) { $("status").textContent = `Errore: ${e.message}`; }
init().catch(fail);
