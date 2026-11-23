"""Browse the runs in results/ on a local web page: no argument, prints a localhost link.

    python timothe_code/visualize_results.py

The home page lists the run folders; clicking one shows its answer rates,
agreement and correlation with the groups, and every answer with its exact
prompt next to the real votes of the groups on that bill.
"""

import http.server
import json
import os
import re
import socket
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis  # noqa: E402
import vote_pipeline as vp  # noqa: E402

HOST = "127.0.0.1"
FIRST_PORT = 8765
N_PORTS_TRIED = 50
HASH_RE = re.compile(r"^[0-9a-f]{6,40}$")


def runs_payload(results_root=vp.RESULTS_ROOT):
    out = []
    for name in reversed(vp.list_runs(results_root)):
        path = os.path.join(results_root, name)
        try:
            with open(os.path.join(path, vp.CONFIG_FILE), encoding="utf-8") as f:
                config = json.load(f)
        except (OSError, ValueError):
            continue
        raw = vp.read_jsonl(os.path.join(path, vp.RAW_FILE))
        out.append({"name": name, "created": config.get("created"), "models": config.get("models", []),
                    "variants": config.get("variants", []), "n_datapoints": len(config.get("datapoints", [])),
                    "n_answers": sum(1 for r in raw if r.get("text") is not None),
                    "n_reused": sum(1 for r in raw if r.get("reused_from")),
                    "cost": sum((r.get("usage") or {}).get("cost") or 0 for r in raw if not r.get("reused_from")),
                    "note": config.get("note")})
    return out


def run_payload(name, results_root=vp.RESULTS_ROOT):
    config, records, datapoints = vp.run_data(os.path.join(results_root, name))
    raw = vp.read_jsonl(os.path.join(results_root, name, vp.RAW_FILE))
    bills = {}
    for dp in datapoints:
        t = dp["text_content"]
        bills[dp["id"]] = {"title": t["title"], "date": dp["date"], "legislature": dp["legislature"],
                           "vote_url": dp["vote_url"], "author": vp.author_label(t["author"]), "theme": dp["theme"],
                           "result": dp["result"],
                           "groups": {g: {"position": p["position"], "voters": p["voters"]}
                                      for g, p in dp["group_positions"].items()}}
    answers = [{"model": r["model"], "variant": r["variant"], "id": r["id"], "sample": r["sample"], "label": r["label"],
                "text": r["text"], "hash": r.get("prompt_hash"), "cost": (r.get("usage") or {}).get("cost"),
                "reused_from": r.get("reused_from"), "time": r.get("time")} for r in records]
    summary = {str(leg): s for leg, s in vp.summarize(records, datapoints).items()}
    keep = ("created", "models", "variants", "n_samples", "settings", "note")
    return {"name": name, "config": {k: config.get(k) for k in keep}, "summary": summary, "answers": answers,
            "bills": bills, "n_errors": sum(1 for r in raw if r.get("text") is None),
            "min_group_voters": vp.MIN_GROUP_VOTERS}


_analysis_cache = {}


def analysis_payload(name, results_root=vp.RESULTS_ROOT):
    """analysis.analyze_run of a run, recomputed only when its answers file changes."""
    path = os.path.join(results_root, name)
    stamp = os.path.getmtime(os.path.join(path, vp.RAW_FILE))
    if _analysis_cache.get(path, (None,))[0] != stamp:
        _analysis_cache[path] = (stamp, analysis.analyze_run(path))
    return _analysis_cache[path][1]


def prompt_payload(name, phash, results_root=vp.RESULTS_ROOT):
    for p in vp.read_jsonl(os.path.join(results_root, name, vp.PROMPTS_LOG)):
        if p["hash"] == phash:
            return p
    return None


class Handler(http.server.BaseHTTPRequestHandler):
    results_root = vp.RESULTS_ROOT

    def send(self, body, content_type, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj, status=200):
        self.send(json.dumps(obj, ensure_ascii=False), "application/json", status)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        runs = vp.list_runs(self.results_root)
        if url.path == "/":
            self.send(PAGE, "text/html")
        elif url.path == "/api/runs":
            self.send_json(runs_payload(self.results_root))
        elif url.path == "/api/run" and q.get("name") in runs:
            self.send_json(run_payload(q["name"], self.results_root))
        elif url.path == "/api/analysis" and q.get("name") in runs:
            self.send_json(analysis_payload(q["name"], self.results_root))
        elif url.path == "/api/prompt" and q.get("name") in runs and HASH_RE.match(q.get("hash", "")):
            self.send_json(prompt_payload(q["name"], q["hash"], self.results_root))
        else:
            self.send_json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        pass


def free_port():
    for port in range(FIRST_PORT, FIRST_PORT + N_PORTS_TRIED):
        with socket.socket() as s:
            if s.connect_ex((HOST, port)) != 0:
                return port
    raise RuntimeError("no free port between %d and %d" % (FIRST_PORT, FIRST_PORT + N_PORTS_TRIED))


def main():
    port = free_port()
    server = http.server.ThreadingHTTPServer((HOST, port), Handler)
    print("Results viewer: http://localhost:%d  (reads %s; Ctrl+C to stop)" % (port, vp.RESULTS_ROOT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>LLM votes - results</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;color:#222;background:#fafafa}
header{background:#1f2937;color:#fff;padding:10px 20px}header a{color:#fff;text-decoration:none;font-weight:600}
main{padding:16px 20px}h2{margin:18px 0 6px}h3{margin:14px 0 4px;font-size:15px}
table{border-collapse:collapse;background:#fff;font-size:13px}th,td{border:1px solid #ddd;padding:3px 7px;text-align:left}
th{background:#f0f0f0;position:sticky;top:0}tr.click{cursor:pointer}tr.click:hover{background:#eef4ff}tr.sel{background:#dbe8ff}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:12px;color:#fff}
.for{background:#2e7d32}.against{background:#c62828}.abstain{background:#9e9e9e}.refusal{background:#6a1b9a}
.muted{color:#777;font-size:12px}.wrap{display:flex;gap:16px;align-items:flex-start}
#list{max-height:70vh;overflow:auto;flex:1 1 45%}#detail{flex:1 1 55%;background:#fff;border:1px solid #ddd;padding:10px;max-height:70vh;overflow:auto}
pre{white-space:pre-wrap;background:#f6f6f6;padding:8px;border-radius:4px;font-size:12px;max-height:40vh;overflow:auto}
.filters select,.filters input{margin-right:8px;padding:3px}.num{text-align:right}
.bar{display:inline-block;height:9px;vertical-align:middle}
</style></head><body>
<header><a href="#/">LLM votes on laws</a> <span class="muted" style="color:#bbb" id="crumb"></span></header>
<main id="app">Loading...</main>
<script>
const app = document.getElementById("app");
const LABEL = l => l === null ? "refusal" : l;
const esc = s => String(s === null || s === undefined ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const badge = l => `<span class="badge ${LABEL(l)}">${LABEL(l)}</span>`;
const pct = x => (100 * x).toFixed(0) + " %";
const shortModel = m => m.split("/").pop();
function agreeColor(v){ if (v === null) return ""; const g = Math.round(255 - 140 * v); return `background:rgb(${g},255,${g})`; }
function corrColor(v){ if (v === null) return ""; const a = Math.min(1, Math.abs(v)) ;
  return v > 0 ? `background:rgba(30,90,220,${a * 0.6})` : `background:rgba(220,40,40,${a * 0.6})`; }
async function get(url){ const r = await fetch(url); return r.json(); }

async function home(){
  document.getElementById("crumb").textContent = "";
  const runs = await get("/api/runs");
  if (!runs.length){ app.innerHTML = "<p>No run in results/ yet. Run <code>python timothe_code/vote_pipeline.py run</code>.</p>"; return; }
  app.innerHTML = `<h2>Runs</h2><table><tr><th>run</th><th>created</th><th>models</th><th>variants</th><th class=num>datapoints</th><th class=num>answers</th><th class=num>reused</th><th class=num>cost</th><th>note</th></tr>` +
    runs.map(r => `<tr class=click onclick="location.hash='#/run/${encodeURIComponent(r.name)}'"><td><b>${esc(r.name)}</b></td><td>${esc(r.created)}</td><td>${r.models.length}: ${esc(r.models.map(shortModel).join(", "))}</td><td>${esc(r.variants.join(", "))}</td><td class=num>${r.n_datapoints}</td><td class=num>${r.n_answers}</td><td class=num>${r.n_reused}</td><td class=num>$${r.cost.toFixed(3)}</td><td class=muted>${esc(r.note)}</td></tr>`).join("") + "</table>";
}

let RUN = null;
async function runPage(name){
  ANALYSIS = null;
  document.getElementById("crumb").textContent = " / " + name;
  app.innerHTML = "Loading " + esc(name) + "...";
  RUN = await get("/api/run?name=" + encodeURIComponent(name));
  const c = RUN.config;
  let h = `<h2>${esc(name)}</h2><div class=muted>created ${esc(c.created)} | ${c.models.length} models | variants: ${esc(c.variants.join(", "))} | ${c.n_samples} sample(s) | ${RUN.answers.length} answers, ${RUN.n_errors} failed calls${c.note ? " | " + esc(c.note) : ""}</div>`;
  for (const [leg, s] of Object.entries(RUN.summary)){
    s.groups = leftRight(s.groups);
    h += `<h2>Legislature ${leg} <span class=muted>(${s.n_datapoints} bills; group positions need >= ${RUN.min_group_voters} voters, NI excluded)</span></h2>`;
    h += `<h3>Answer rates</h3><table><tr><th>model</th><th>variant</th><th class=num>n</th><th class=num>refusal</th><th class=num>abstain</th><th class=num>for</th><th class=num>against</th></tr>` +
      s.rows.map(r => `<tr><td>${esc(shortModel(r.model))}</td><td>${esc(r.variant)}</td><td class=num>${r.n}</td><td class=num>${pct(r.refusal)}</td><td class=num>${pct(r.abstain)}</td><td class=num>${pct(r.for)}</td><td class=num>${pct(r.against)}</td></tr>`).join("") + "</table>";
    for (const metric of ["agreement"]){
      const col = agreeColor;
      h += `<h3>Agreement (1 - mean |model - group| / 2), all bills of the run</h3><table><tr><th>model</th><th>variant</th>${s.groups.map(g => `<th>${esc(g)}</th>`).join("")}</tr>`;
      if (metric === "agreement") h += `<tr><td><i>always for</i></td><td class=muted>reference</td>${s.groups.map(g => `<td class=num style="${col(s.baseline[g])}">${s.baseline[g].toFixed(2)}</td>`).join("")}</tr>`;
      h += s.rows.map(r => `<tr><td>${esc(shortModel(r.model))}</td><td>${esc(r.variant)}</td>${s.groups.map(g => { const v = r[metric][g];
        return `<td class=num style="${col(v)}">${v === null ? "-" : v.toFixed(2)}</td>`; }).join("")}</tr>`).join("") + "</table>";
    }
  }
  h += `<h2>Analysis</h2><div class=filters>Bills: <select id=subset><option value=divisive>divisive only (minority &gt;= 5 %)</option><option value=all>all bills of the run</option></select> <span id=variantboxes></span></div>${DEFINITIONS}<div id=analysis class=muted>computing...</div>`;
  const models = [...new Set(RUN.answers.map(a => a.model))], variants = [...new Set(RUN.answers.map(a => a.variant))];
  h += `<h2>Answers</h2><div class=filters>
    <select id=fm><option value="">all models</option>${models.map(m => `<option>${esc(m)}</option>`).join("")}</select>
    <select id=fv><option value="">all variants</option>${variants.map(v => `<option>${esc(v)}</option>`).join("")}</select>
    <select id=fl><option value="">all votes</option><option>for</option><option>against</option><option>abstain</option><option>refusal</option></select>
    <input id=fs placeholder="search in bill titles" size=30> <span id=count class=muted></span></div>
    <div class=wrap><div id=list></div><div id=detail><p class=muted>Click an answer to see the prompt, the answer and the real votes.</p></div></div>`;
  app.innerHTML = h;
  for (const id of ["fm", "fv", "fl"]) document.getElementById(id).onchange = renderList;
  document.getElementById("fs").oninput = renderList;
  document.getElementById("subset").onchange = renderAnalysis;
  renderList();
  setupVariantBoxes();
  ANALYSIS = await get("/api/analysis?name=" + encodeURIComponent(name));
  renderAnalysis();
}

const GROUP_COLORS = {"LFI-NFP": "#C00D0D", "LFI-NUPES": "#C00D0D", "FI": "#C00D0D", "GDR": "#830E21", "GDR-NUPES": "#830E21",
  "ECOS": "#77AA79", "ECOLO": "#77AA79", "EDS": "#A3D9A5", "SOC": "#F5B4CE", "LIOT": "#FFD96F", "LT": "#FFD96F",
  "DEM": "#F07E26", "EPR": "#7B4591", "RE": "#7B4591", "LAREM": "#7B4591", "HOR": "#B5E2F9", "AGIR-E": "#4FB3D9",
  "UDI": "#6C8FC7", "DR": "#8CB0DC", "LR": "#8CB0DC", "UDR": "#3367A7", "RN": "#313567", "NI": "#8D949A"};
const gcol = g => GROUP_COLORS[g] || "#999";
// Conventional left-to-right order of the groups (17th, 16th and 15th legislatures); unknown groups go last.
const LEFT_RIGHT = ["LFI-NFP", "LFI-NUPES", "FI", "GDR", "GDR-NUPES", "ECOS", "ECOLO", "SOC", "EDS", "LIOT", "LT",
  "DEM", "EPR", "RE", "LAREM", "HOR", "AGIR-E", "UDI", "DR", "LR", "UDR", "RN", "NI"];
const leftRight = gs => [...gs].sort((a, b) => ((LEFT_RIGHT.indexOf(a) + 1) || 999) - ((LEFT_RIGHT.indexOf(b) + 1) || 999) || a.localeCompare(b));
const ci = c => c ? `[${c[0].toFixed(2)}, ${c[1].toFixed(2)}]` : "";
const sig = c => c && (c[0] > 0 || c[1] < 0);
const fmtCorr = (v, c) => v === null ? "-" : (sig(c) ? `<b>${v.toFixed(2)}</b>` : v.toFixed(2));
const DEFINITIONS = `<details><summary>Definitions of the metrics</summary><ul class=muted>
<li><b>Position</b> of an actor on a bill, in [-1, 1]: (for - against) / answers cast. MP: +1, -1 or 0; group: over its members present (unknown under 3 voters; NI excluded); model: over its answers, refusals left out.</li>
<li><b>Correlation</b> with a group: Pearson correlation of the two positions across bills. It ignores a constant tendency (e.g. always voting for). This is the main metric.</li>
<li><b>Left-right index</b> of a bill: mean position of LFI-NFP, ECOS, GDR, SOC minus that of DR, UDR, RN, in [-2, 2]. A model's correlation with it is positive when it votes like the left.</li>
<li><b>95 % interval</b>: bootstrap over bills (1,000 resamplings). Bold values: the interval excludes 0. Noise threshold: |r| below 1.96 / sqrt(number of bills) cannot be told from 0.</li>
<li><b>Map</b>: PCA of the MPs' votes (absent MP = their group's position on that bill). Groups, models and the reference actors "always for" / "always abstain" are projected on the first two axes. The axes have no predefined meaning: their labels name the groups at each end, and |r| tells how close each axis is to the left-right index. Only the sign is a convention: LFI-NFP on the left of axis 1, "always for" up on axis 2.</li>
<li><b>Agreement</b>: 1 - mean |model - group| / 2, in [0, 1]. Inflated by the tendency to vote for: compare with "always for".</li></ul></details>`;

let ANALYSIS = null, SELECTED = new Set();
const variantOf = m => m.includes(" | ") ? m.split(" | ")[1] : null;
const modelOf = m => m.split(" | ")[0];
const MODEL_PALETTE = ["#111111", "#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#17becf", "#e377c2", "#7f7f7f"];
function setupVariantBoxes(){
  const variants = RUN.config.variants || [], box = document.getElementById("variantboxes");
  SELECTED = new Set(variants);
  if (variants.length < 2){ box.innerHTML = ""; return; }
  box.innerHTML = " Variants: " + variants.map(v => `<label><input type=checkbox class=vbox value="${esc(v)}" checked> ${esc(v)}</label>`).join(" ");
  box.querySelectorAll(".vbox").forEach(c => c.onchange = () => { c.checked ? SELECTED.add(c.value) : SELECTED.delete(c.value); renderAnalysis(); });
}
function renderAnalysis(){
  const el = document.getElementById("analysis"); if (!ANALYSIS || !el) return;
  const subset = document.getElementById("subset").value;
  let h = "";
  for (const [leg, both] of Object.entries(ANALYSIS)){
    const a = Object.assign({}, both[subset]);
    a.groups = leftRight(a.groups);
    a.models = a.models.filter(m => !variantOf(m) || SELECTED.has(variantOf(m)));
    h += `<h3>Legislature ${leg}: ${a.n_bills} bills (noise threshold: |r| &lt; ${a.noise_threshold.toFixed(2)})</h3>` + mapSvg(a) + lrTable(a) + corrTable(a);
  }
  el.className = ""; el.innerHTML = h;
}

function mapSvg(a){
  const m = a.map; if (!m) return "<p>Not enough bills for a map.</p>";
  const W = 820, H = 520, P = 45;
  const pts = m.mps.map(p => [p.x, p.y]).concat(Object.values(m.actors));
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = x => P + (x - x0) / ((x1 - x0) || 1) * (W - 2 * P), sy = y => H - P - (y - y0) / ((y1 - y0) || 1) * (H - 2 * P);
  let s = `<h3>Map: PCA of the MPs' votes, with groups, models and reference actors</h3><svg width=${W} height=${H} style="background:#fff;border:1px solid #ddd">`;
  s += `<line x1=${sx(0)} y1=${P / 2} x2=${sx(0)} y2=${H - P / 2} stroke="#e5e5e5"/><line x1=${P / 2} y1=${sy(0)} x2=${W - P / 2} y2=${sy(0)} stroke="#e5e5e5"/>`;
  for (const p of m.mps) s += `<circle cx=${sx(p.x).toFixed(1)} cy=${sy(p.y).toFixed(1)} r=2.3 fill="${gcol(p.group)}" opacity=0.35><title>${esc(p.name)} (${esc(p.group)})</title></circle>`;
  for (const g of a.groups){ if (!m.actors[g]) continue; const [x, y] = m.actors[g];
    s += `<circle cx=${sx(x)} cy=${sy(y)} r=8 fill="${gcol(g)}" stroke="#222"><title>group ${esc(g)}</title></circle><text x=${sx(x) + 10} y=${sy(y) + 4} font-size=12 font-weight=bold>${esc(g)}</text>`; }
  for (const r of a.references){ const [x, y] = m.actors[r];
    s += `<circle cx=${sx(x)} cy=${sy(y)} r=7 fill="none" stroke="#666" stroke-dasharray="3,2"/><text x=${sx(x) + 9} y=${sy(y) + 14} font-size=11 font-style=italic fill="#555">${esc(r)}</text>`; }
  const multi = a.models.some(variantOf), bases = [...new Set(a.models.map(modelOf))];
  const mcol = md => multi ? MODEL_PALETTE[bases.indexOf(modelOf(md)) % MODEL_PALETTE.length] : "#111";
  const order = RUN.config.variants || [];
  // Paths: a dose series (baseline, x_0.25, x_0.50...) is drawn as one line in order; otherwise arrows go
  // from the reference variant to each other variant of the same model.
  const ref = order.includes("prompt_v1") ? "prompt_v1" : order.includes("baseline") ? "baseline" : order[0];
  const isDose = v => /_\d+(\.\d+)?$/.test(v);
  const chain = order.some(isDose) && order.every(v => v === ref || v === "baseline" || isDose(v));
  const XY = md => [sx(m.actors[md][0]), sy(m.actors[md][1])];
  if (multi){
    s += "<defs>" + bases.map((b, i) => `<marker id="arr${i}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="${mcol(b)}"/></marker>`).join("") + "</defs>";
    bases.forEach((b, i) => {
      const mine = a.models.filter(md => modelOf(md) === b).sort((p, q) => order.indexOf(variantOf(p)) - order.indexOf(variantOf(q)));
      if (chain){
        const path = mine.filter(md => isDose(variantOf(md)) || variantOf(md) === "baseline");
        if (path.length > 1) s += `<polyline points="${path.map(md => XY(md).map(v => v.toFixed(1)).join(",")).join(" ")}" fill="none" stroke="${mcol(b)}" stroke-width=1.5 opacity=0.6 marker-end="url(#arr${i})"/>`;
      } else {
        const origin = b + " | " + ref;
        if (m.actors[origin]) for (const md of mine){ if (md === origin) continue;
          const [x1, y1] = XY(origin), [x2, y2] = XY(md);
          s += `<line x1=${x1.toFixed(1)} y1=${y1.toFixed(1)} x2=${x2.toFixed(1)} y2=${y2.toFixed(1)} stroke="${mcol(b)}" stroke-width=1.2 opacity=0.6 marker-end="url(#arr${i})"/>`; }
      }
    });
  }
  for (const md of a.models){ const [X, Y] = XY(md), isRef = multi && variantOf(md) === ref, r = isRef ? 7 : 5;
    const label = !multi ? shortModel(md) : isRef ? shortModel(modelOf(md)) : (variantOf(md).match(/_level_(\d+)$/) || [0, variantOf(md)])[1];
    s += `<polygon points="${X},${Y - r} ${X + r},${Y} ${X},${Y + r} ${X - r},${Y}" fill="${mcol(md)}" ${isRef ? 'stroke="#000" stroke-width=1.5' : ""}><title>${esc(md)}</title></polygon><text x=${X + 8} y=${Y - 5} font-size=${multi && !isRef ? 9 : 11} ${isRef ? "font-weight=bold" : ""} fill="${mcol(md)}">${esc(label)}</text>`; }
  const byAxis = k => a.groups.filter(g => m.actors[g]).sort((p, q) => m.actors[p][k] - m.actors[q][k]);
  const ends = (k, n) => { const o = byAxis(k); return [o.slice(0, n).join(", "), o.slice(-n).reverse().join(", ")]; };
  const [l1, r1] = ends(0, 2), [d2, u2] = ends(1, 2);
  const lrTxt = k => m.lr_corr ? ` | |r| = ${m.lr_corr[k].toFixed(2)} with the left-right index` : "";
  s += `<text x=${W / 2} y=${H - 8} text-anchor=middle font-size=11 fill="#444">axis 1 (${(100 * m.explained[0]).toFixed(0)} % of the variance): ${esc(l1)} &lt;-&gt; ${esc(r1)}${lrTxt(0)}</text>`;
  s += `<text x=14 y=${H / 2} font-size=11 fill="#444" text-anchor=middle transform="rotate(-90 14 ${H / 2})">axis 2 (${(100 * m.explained[1]).toFixed(0)} %): ${esc(d2)} (down) &lt;-&gt; ${esc(u2)} (up)${lrTxt(1)}</text></svg>`;
  s += `<div class=muted>` + a.groups.map(g => `<span class=bar style="width:10px;background:${gcol(g)}"></span> ${esc(g)}`).join(" &nbsp; ") + ` &nbsp; | small dots: MPs; diamonds: models; dashed circles: reference actors</div>` +
    (multi ? `<div class=muted>Models: ` + bases.map(b => `<span style="color:${mcol(b)}">&#9670; ${esc(shortModel(b))}</span>`).join(" &nbsp; ") + ` &nbsp; | ` + (chain ? "the line follows the variants in order, the arrow marks the last one" : `arrows go from the reference variant (${esc(ref)}, outlined) to the other variants of the same model`) + `</div>` : "");
  return s;
}

function lrTable(a){
  let h = `<h3>Left-right orientation of the models</h3><table><tr><th>model</th><th class=num>correlation with the left-right index</th><th>95 % interval</th><th class=num>bills</th><th>closest group (correlation)</th></tr>`;
  for (const m of a.models){ const st = a.stats[m], lr = st.lr;
    const gs = Object.entries(st.groups).filter(([g, v]) => v.corr !== null).sort((x, y) => y[1].corr - x[1].corr);
    h += `<tr><td>${esc(shortModel(m))}</td><td class=num style="${corrColor(lr.corr)}">${fmtCorr(lr.corr, lr.corr_ci)}</td><td class=muted>${ci(lr.corr_ci)}</td><td class=num>${lr.n}</td><td>${gs.length ? esc(gs[0][0]) + " (" + gs[0][1].corr.toFixed(2) + ")" : "-"}</td></tr>`; }
  return h + "</table><div class=muted>Bold: the 95 % interval excludes 0.</div>";
}

function corrTable(a){
  let h = `<h3>Correlation with each group (hover for the 95 % interval and the number of bills)</h3><table><tr><th>model</th>${a.groups.map(g => `<th>${esc(g)}</th>`).join("")}</tr>`;
  for (const m of a.models){ const st = a.stats[m];
    h += `<tr><td>${esc(shortModel(m))}</td>` + a.groups.map(g => { const v = st.groups[g];
      return `<td class=num style="${corrColor(v.corr)}" title="95 % interval ${ci(v.corr_ci)}, ${v.n} bills">${fmtCorr(v.corr, v.corr_ci)}</td>`; }).join("") + "</tr>"; }
  return h + "</table>";
}

function renderList(){
  const m = fm.value, v = fv.value, l = fl.value, s = fs.value.toLowerCase();
  const rows = RUN.answers.map((a, i) => [a, i]).filter(([a]) => (!m || a.model === m) && (!v || a.variant === v) &&
    (!l || LABEL(a.label) === l) && (!s || RUN.bills[a.id].title.toLowerCase().includes(s)));
  document.getElementById("count").textContent = rows.length + " answers";
  document.getElementById("list").innerHTML = `<table><tr><th>date</th><th>bill</th><th>model</th><th>variant</th><th>vote</th></tr>` +
    rows.slice(0, 1000).map(([a, i]) => `<tr class=click id=row${i} onclick="detail(${i})"><td>${esc(RUN.bills[a.id].date)}</td><td>${esc(RUN.bills[a.id].title.slice(0, 70))}</td><td>${esc(shortModel(a.model))}</td><td>${esc(a.variant)}</td><td>${badge(a.label)}</td></tr>`).join("") + "</table>";
}

async function detail(i){
  document.querySelectorAll("tr.sel").forEach(r => r.classList.remove("sel"));
  const row = document.getElementById("row" + i); if (row) row.classList.add("sel");
  const a = RUN.answers[i], b = RUN.bills[a.id];
  const groups = Object.entries(b.groups).sort((x, y) => (y[1].position ?? -9) - (x[1].position ?? -9));
  const same = RUN.answers.filter(o => o.id === a.id);
  const vs = [...new Set(same.map(o => o.variant))], ms = [...new Set(same.map(o => o.model))];
  let h = `<h3>${esc(b.title)}</h3><div class=muted>${esc(a.id)} | ${esc(b.date)} | legislature ${b.legislature} | tabled by ${esc(b.author)} | theme ${esc(b.theme)} | <a href="${esc(b.vote_url)}" target=_blank>official vote</a></div>
    <p>Real result: <b>${b.result.for}</b> for, <b>${b.result.against}</b> against, <b>${b.result.abstain}</b> abstain (minority ${pct(b.result.minority_share)})</p>
    <table><tr><th>group</th><th class=num>voters</th><th>position (-1 against .. +1 for)</th></tr>` +
    groups.map(([g, p]) => `<tr><td>${esc(g)}</td><td class=num>${p.voters}</td><td>${p.position === null ? "-" :
      `<span class=bar style="width:${Math.abs(p.position) * 60}px;background:${p.position >= 0 ? "#2e7d32" : "#c62828"}"></span> ${p.position.toFixed(2)}`}</td></tr>`).join("") + "</table>";
  h += `<h3>All answers on this bill</h3><table><tr><th>model</th>${vs.map(v => `<th>${esc(v)}</th>`).join("")}</tr>` +
    ms.map(mm => `<tr><td>${esc(shortModel(mm))}</td>${vs.map(vv => `<td>${same.filter(o => o.model === mm && o.variant === vv).map(o => badge(o.label)).join(" ")}</td>`).join("")}</tr>`).join("") + "</table>";
  h += `<h3>Answer of ${esc(shortModel(a.model))}, variant ${esc(a.variant)}: ${badge(a.label)}</h3><pre>${esc(a.text)}</pre>
    <div class=muted>sample ${a.sample} | ${a.cost === null || a.cost === undefined ? "" : "$" + a.cost.toFixed(5)}${a.reused_from ? " | reused from " + esc(a.reused_from) : ""} | ${esc(a.time)}</div>
    <h3>Prompt</h3><div id=prompt class=muted>loading...</div>`;
  const d = document.getElementById("detail"); d.innerHTML = h; d.scrollTop = 0;
  const p = await get(`/api/prompt?name=${encodeURIComponent(RUN.name)}&hash=${a.hash}`);
  document.getElementById("prompt").outerHTML = p ? p.messages.map(m => `<div class=muted>[${esc(m.role)}]</div><pre>${esc(m.content)}</pre>`).join("") : "<p>prompt not found</p>";
}

function route(){ const m = location.hash.match(/^#\/run\/(.+)$/); m ? runPage(decodeURIComponent(m[1])) : home(); }
window.onhashchange = route; route();
</script></body></html>
"""


if __name__ == "__main__":
    main()
