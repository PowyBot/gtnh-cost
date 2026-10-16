"use strict";
// Flow diagram of a recipe chain: raw materials on the left, the item on the right, each band as wide as the
// amount that flows through it. A layered Sankey drawn by hand in SVG, no library.
//
// Bands taper on purpose: in GT a recipe rarely conserves amounts (1 ore -> 2 crushed ore), so a band leaves its
// input as wide as the amount used and reaches its product as that input's share of what the product needs.

const FLOW = {
  maxNodes: 45,      // above this, nodes far from the item start folded: big chains stay readable on a phone
  nodeWidth: 10,
  padding: 10,       // vertical gap between nodes of one column
  minHeight: 3,      // a trace still gets a visible node
  labelGap: 13,      // px between label baselines, a bit more than the 11px font
  charWidth: 6,      // average width of an 11px system-ui character, to cut labels before the next column
  sweeps: 8,         // barycenter passes to untangle crossing bands
};
const SVG_NS = "http://www.w3.org/2000/svg";

// Demand of every item in the chain and the links between them, walking the chosen recipes as a DAG.
// isLeaf(item) says where to stop (raw, folded, "stop at ingots"); a recipe loop is cut where it closes.
function flowGraph(how, root, n, isLeaf) {
  const order = [], state = new Map(); // 1 = on the DFS path, 2 = done
  const visit = (item) => {
    state.set(item, 1);
    if (!isLeaf(item)) {
      const inputs = how[item][4];
      for (let k = 0; k < inputs.length; k += 2) if (!state.has(inputs[k])) visit(inputs[k]);
    }
    state.set(item, 2);
    order.push(item);
  };
  visit(root);
  order.reverse(); // every item now comes before its inputs
  const need = new Map([[root, n]]), links = new Map(), position = new Map(order.map((item, k) => [item, k]));
  for (const item of order) {
    const amount = need.get(item) || 0;
    if (isLeaf(item) || !amount) continue;
    const [, , , made, inputs] = how[item], runs = amount / made;
    for (let k = 0; k < inputs.length; k += 2) {
      const input = inputs[k];
      if (position.get(input) <= position.get(item)) continue; // closes a loop: the expansion stops there too
      need.set(input, (need.get(input) || 0) + inputs[k + 1] * runs);
      const key = `${input}>${item}`;
      links.set(key, { from: input, to: item, amount: (links.get(key)?.amount || 0) + inputs[k + 1] * runs });
    }
  }
  return { order, need, links: [...links.values()] };
}

// Which items start folded: the ones with a recipe whose shortest distance from the item is at or past the first
// depth at which the chain would exceed FLOW.maxNodes.
function defaultFolds(how, root, n, isLeaf) {
  const { order, links } = flowGraph(how, root, n, isLeaf);
  if (order.length <= FLOW.maxNodes) return new Set();
  const depth = new Map([[root, 0]]), queue = [root], inputsOf = new Map();
  for (const l of links) inputsOf.set(l.to, [...(inputsOf.get(l.to) || []), l.from]);
  while (queue.length) {
    const item = queue.shift();
    for (const input of inputsOf.get(item) || []) {
      if (depth.has(input)) continue;
      depth.set(input, depth.get(item) + 1);
      queue.push(input);
    }
  }
  const perDepth = [];
  for (const d of depth.values()) perDepth[d] = (perDepth[d] || 0) + 1;
  let cut = 0, seen = 0;
  while (cut < perDepth.length && seen + perDepth[cut] <= FLOW.maxNodes) seen += perDepth[cut++];
  // folding at the cut keeps the nodes up to it; the folded ones are the last column on the left
  return new Set([...depth].filter(([item, d]) => d >= Math.max(cut - 1, 1) && !isLeaf(item)).map(([item]) => item));
}

function layoutFlow(graph, value, height) {
  const { order, links } = graph;
  const ins = new Map(order.map((i) => [i, []])), outs = new Map(order.map((i) => [i, []]));
  for (const l of links) { ins.get(l.to).push(l); outs.get(l.from).push(l); }
  // column = longest path from a leaf: raw materials at 0, the item last
  const col = new Map();
  for (const item of [...order].reverse()) col.set(item, Math.max(-1, ...ins.get(item).map((l) => col.get(l.from))) + 1);
  const columns = [];
  for (const item of order) (columns[col.get(item)] ||= []).push(item);
  const total = (c) => c.reduce((s, i) => s + value(i), 0);
  const ky = Math.min(...columns.map((c) => (height - FLOW.padding * (c.length - 1)) / (total(c) || 1)));
  const h = new Map(order.map((i) => [i, Math.max(value(i) * ky, FLOW.minHeight)]));
  const y = new Map(), center = (i) => y.get(i) + h.get(i) / 2;
  const place = (c) => {
    let top = 0;
    for (const i of c) { y.set(i, top); top += h.get(i) + FLOW.padding; }
  };
  columns.forEach(place);
  // Barycenter heuristic: order each column by the weighted centers of its neighbours, both directions.
  const sortBy = (c, edges, other) => {
    const at = (i) => {
      const es = edges.get(i);
      const w = es.reduce((s, l) => s + l.amount, 0);
      return w ? es.reduce((s, l) => s + center(l[other]) * l.amount, 0) / w : center(i);
    };
    const keyed = new Map(c.map((i) => [i, at(i)]));
    c.sort((a, b) => keyed.get(a) - keyed.get(b));
    place(c);
  };
  for (let s = 0; s < FLOW.sweeps; s++) {
    for (const c of columns.slice(1)) sortBy(c, ins, "from");
    for (const c of columns.slice(0, -1).reverse()) sortBy(c, outs, "to");
  }
  const tallest = Math.max(...columns.map((c) => y.get(c.at(-1)) + h.get(c.at(-1))));
  for (const c of columns) {
    const shift = (tallest - (y.get(c.at(-1)) + h.get(c.at(-1)))) / 2;
    for (const i of c) y.set(i, y.get(i) + shift);
  }
  // Band ends: leaving its input, a band takes its share of the input's height; reaching the product, its share
  // of the product's height among all the product's inputs.
  const bands = links.map((l) => ({ ...l }));
  const stack = (item, end, other) => {
    const list = bands.filter((b) => b[end] === item).sort((a, b) => center(a[other]) - center(b[other]));
    const sum = list.reduce((s, b) => s + edgeValue(b), 0) || 1;
    let top = y.get(item);
    for (const b of list) {
      const w = h.get(item) * edgeValue(b) / sum;
      b[end + "Y"] = top;
      b[end + "H"] = w;
      top += w;
    }
  };
  const edgeValue = (b) => value(b.from) * b.amount / (graph.need.get(b.from) || 1);
  for (const item of order) { stack(item, "from", "to"); stack(item, "to", "from"); }
  return { col, columns, y, h, bands, height: tallest };
}

function svg(tag, attrs, parent) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (parent) parent.append(el);
  return el;
}

// Draws the chain into box. opts: how, root, n, isLeaf(item), folded(item) -> bool, toggle(item),
// value(item) -> band size, label(item) -> name, amountText(item, amount), color(item), details(item, amount) -> text.
function drawFlow(box, opts) {
  const graph = flowGraph(opts.how, opts.root, opts.n, (i) => opts.isLeaf(i) || opts.folded(i));
  const narrow = box.clientWidth < 600, labelRoom = narrow ? 130 : 200;
  const height = Math.max(320, Math.min(1000, graph.order.length * 14));
  const value = (i) => opts.value(i, graph.need.get(i));
  const lay = layoutFlow(graph, value, height);
  // fill the box when the columns fit, scroll sideways (phones, long chains) when they don't
  const fit = (box.clientWidth - labelRoom - FLOW.nodeWidth - 24) / Math.max(lay.columns.length - 1, 1);
  const colWidth = Math.min(Math.max(fit, narrow ? 130 : 110), 260);
  const width = (lay.columns.length - 1) * colWidth + FLOW.nodeWidth + labelRoom;
  const root = svg("svg", { viewBox: `-4 -4 ${width + 8} ${lay.height + 8}`, width: width + 8, height: lay.height + 8, class: "flow" });
  const x = (i) => lay.col.get(i) * colWidth;
  const bandLayer = svg("g", {}, root), nodeLayer = svg("g", {}, root);
  const paths = [];
  for (const b of lay.bands) {
    const x0 = x(b.from) + FLOW.nodeWidth, x1 = x(b.to), xm = (x0 + x1) / 2;
    const d = `M${x0},${b.fromY}C${xm},${b.fromY} ${xm},${b.toY} ${x1},${b.toY}` +
      `L${x1},${b.toY + b.toH}C${xm},${b.toY + b.toH} ${xm},${b.fromY + b.fromH} ${x0},${b.fromY + b.fromH}Z`;
    const p = svg("path", { d, fill: opts.color(b.from), class: "band" }, bandLayer);
    p.dataset.from = b.from;
    p.dataset.to = b.to;
    p.addEventListener("pointerenter", (e) => tip(e, `${opts.label(b.from)} → ${opts.label(b.to)}: ${opts.amountText(b.from, b.amount)}`));
    p.addEventListener("pointerleave", untip);
    paths.push(p);
  }
  const tipBox = box.querySelector(".flowtip") || Object.assign(document.createElement("div"), { className: "flowtip" });
  tipBox.hidden = true;
  function tip(e, text) {
    tipBox.textContent = text;
    tipBox.hidden = false;
    const r = box.getBoundingClientRect();
    tipBox.style.left = `${Math.min(e.clientX - r.left + box.scrollLeft + 12, box.scrollLeft + box.clientWidth - 230)}px`;
    tipBox.style.top = `${e.clientY - r.top + box.scrollTop + 12}px`;
  }
  function untip() { tipBox.hidden = true; highlight(null); }
  function highlight(item) {
    for (const p of paths) p.classList.toggle("lit", item !== null && (+p.dataset.from === item || +p.dataset.to === item));
    root.classList.toggle("focus", item !== null);
  }
  let touched = null; // on a touch screen the first tap shows details, the second folds or opens
  // Small neighbours would print their names on top of each other: a label needs FLOW.labelGap from the one above.
  const labelled = new Set();
  for (const c of lay.columns) {
    let free = -Infinity;
    for (const item of [...c].sort((a, b) => lay.y.get(a) - lay.y.get(b))) {
      const mid = lay.y.get(item) + lay.h.get(item) / 2;
      if (mid < free && item !== opts.root) continue;
      labelled.add(item);
      free = mid + FLOW.labelGap;
    }
  }
  for (const item of graph.order) {
    const g = svg("g", { class: "node", transform: `translate(${x(item)},${lay.y.get(item)})` }, nodeLayer);
    const canFold = !opts.isLeaf(item) && item !== opts.root;
    const folded = opts.folded(item) && !opts.isLeaf(item);
    svg("rect", { width: FLOW.nodeWidth, height: lay.h.get(item), fill: opts.color(item), class: folded ? "folded" : "" }, g);
    if (labelled.has(item)) {
      const text = svg("text", { x: FLOW.nodeWidth + 5, y: lay.h.get(item) / 2, dy: "0.35em" }, g);
      const full = `${folded ? "⊕ " : ""}${opts.label(item)} · ${opts.amountText(item, graph.need.get(item))}`;
      const room = lay.col.get(item) === lay.columns.length - 1 ? Infinity : Math.floor((colWidth - 16) / FLOW.charWidth);
      text.textContent = full.length > room ? full.slice(0, room - 1) + "…" : full;
    }
    if (canFold || folded) g.classList.add("toggle");
    const info = () => opts.details(item, graph.need.get(item)) + (folded ? "\n(tocca di nuovo per aprire)" : canFold ? "\n(tocca di nuovo per chiudere)" : "");
    g.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") { tip(e, info().replace(/\n\(tocca.*\)$/, "")); highlight(item); } });
    g.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") untip(); });
    g.addEventListener("click", (e) => {
      const touch = e.pointerType === "touch" || e.pointerType === "pen" || matchMedia("(hover: none)").matches;
      if (touch && touched !== item) {
        touched = item;
        tip(e, info());
        highlight(item);
        return;
      }
      touched = null;
      if (canFold || folded) opts.toggle(item);
    });
  }
  box.replaceChildren(root, tipBox);
  return graph;
}
