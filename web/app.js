"use strict";
// Stessa espansione di cost.py, sui file precalcolati da web/export.py.
const TIERS = ["ULV", "LV", "MV", "HV", "EV", "IV", "LuV", "ZPM", "UV", "UHV", "UEV", "UIV", "UMV", "UXV", "OpV", "MAX"];
const $ = (id) => document.getElementById(id);
let items = [], lower = [], byId = new Map(), tiers = new Map(), selected = null;

// arrotonda come Python (valore binario esatto, pari a metà), così i numeri coincidono con la CLI
function pyFixed(a, d) {
  const exact = a.toFixed(100), dot = exact.indexOf(".");
  const head = exact.slice(0, d ? dot + 1 + d : dot), tail = exact.slice(dot + 1 + d);
  return /^50*$/.test(tail) && +head.at(-1) % 2 === 0 ? head : a.toFixed(d);
}
const fmt = (i, a) => items[i][2] ? `${pyFixed(a, 0)} L` : pyFixed(a, 2).replace(/0+$/, "").replace(/\.$/, "");
const tierLabel = (t) => t === "MAX" ? "tutti (MAX)" : t;

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function loadTier(t) {
  if (!tiers.has(t)) tiers.set(t, getJSON(`data/${t}.json`).catch((e) => { tiers.delete(t); throw e; }));
  return tiers.get(t);
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
  if (!how || path.has(item)) { raw.set(item, (raw.get(item) || 0) + amount); return; }
  const [machine, , , made, inputs] = how, runs = amount / made, key = `${machine} ${item}`;
  steps.set(key, [machine, item, (steps.get(key)?.[2] || 0) + runs]);
  path.add(item);
  for (let k = 0; k < inputs.length; k += 2) expand(data, inputs[k], inputs[k + 1] * runs, raw, steps, path);
  path.delete(item);
}

function node(data, item, amount, path) {
  const how = data.how[item], cyc = path.includes(item);
  const label = `<span class="amt">${fmt(item, amount)}</span> <span class="name"></span>`;
  if (!how || cyc) {
    const div = document.createElement("div");
    div.className = "leaf";
    div.innerHTML = label + (items[item][3] ? "" : ` <span class="warn">(?)</span>`);
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

async function submit() {
  const tier = $("tier").value, n = Math.max(+$("n").value || 1, 1e-9);
  if (selected === null) {
    const hit = search($("q").value)[0];
    if (hit === undefined) { $("status").textContent = "Nessun oggetto con quel nome."; return; }
    selected = hit;
    $("q").value = items[hit][1];
  }
  const params = new URLSearchParams({ item: items[selected][0], tier, n });
  history.replaceState(null, "", `?${params}`);
  $("status").textContent = "Calcolo…";
  const data = await loadTier(tier), item = selected;
  if (data.cost[item] === null) { $("status").textContent = "Irraggiungibile."; $("result").hidden = true; return; }
  const raw = new Map(), steps = new Map();
  expand(data, item, n, raw, steps, new Set());
  $("title").textContent = `${n} × ${items[item][1]} — tier ${tierLabel(tier)} — costo ${pyFixed(data.cost[item] * n, 2)}`;
  $("raw").tBodies[0].replaceChildren(...[...raw].sort((a, b) => b[1] * (data.cost[b[0]] ?? 1) - a[1] * (data.cost[a[0]] ?? 1)).map(([r, a]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num"></td><td></td>`;
    tr.cells[0].textContent = fmt(r, a);
    tr.cells[1].textContent = items[r][1] + (items[r][3] ? "" : " (?) nessuna ricetta: da trovare/comprare");
    if (!items[r][3]) tr.className = "warn";
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
  const root = node(data, item, n, []);
  if (root.tagName === "DETAILS") root.open = true;
  $("tree").replaceChildren(root);
  $("result").hidden = false;
  $("status").textContent = "";
}

async function init() {
  $("tier").innerHTML = TIERS.map((t) => `<option value="${t}">${tierLabel(t)}</option>`).join("");
  const p = new URLSearchParams(location.search);
  $("tier").value = TIERS.includes(p.get("tier")) ? p.get("tier") : "LV";
  if (p.get("n")) $("n").value = p.get("n");
  items = await getJSON("data/items.json");
  lower = items.map((x) => x[1].toLowerCase());
  items.forEach((x, i) => byId.set(x[0], i));
  $("q").disabled = false;
  $("status").textContent = "";
  $("q").addEventListener("input", () => { selected = null; showSuggest(search($("q").value)); });
  $("q").addEventListener("blur", () => { $("suggest").hidden = true; });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("suggest").hidden = true;
  });
  $("form").addEventListener("submit", (e) => { e.preventDefault(); $("suggest").hidden = true; submit().catch(fail); });
  $("tier").addEventListener("change", () => { if (!$("result").hidden) submit().catch(fail); });
  $("share").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(location.href); $("share").textContent = "Copiato!"; }
    catch { prompt("Link:", location.href); }
  });
  if (byId.has(p.get("item"))) choose(byId.get(p.get("item")));
}

function fail(e) { $("status").textContent = `Errore: ${e.message}`; }
init().catch(fail);
