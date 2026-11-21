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
  document.getElementById("crumb").textContent = " / " + name;
  app.innerHTML = "Loading " + esc(name) + "...";
  RUN = await get("/api/run?name=" + encodeURIComponent(name));
  const c = RUN.config;
  let h = `<h2>${esc(name)}</h2><div class=muted>created ${esc(c.created)} | ${c.models.length} models | variants: ${esc(c.variants.join(", "))} | ${c.n_samples} sample(s) | ${RUN.answers.length} answers, ${RUN.n_errors} failed calls${c.note ? " | " + esc(c.note) : ""}</div>`;
  for (const [leg, s] of Object.entries(RUN.summary)){
    h += `<h2>Legislature ${leg} <span class=muted>(${s.n_datapoints} bills; group positions need >= ${RUN.min_group_voters} voters, NI excluded)</span></h2>`;
    h += `<h3>Answer rates</h3><table><tr><th>model</th><th>variant</th><th class=num>n</th><th class=num>refusal</th><th class=num>abstain</th><th class=num>for</th><th class=num>against</th></tr>` +
      s.rows.map(r => `<tr><td>${esc(shortModel(r.model))}</td><td>${esc(r.variant)}</td><td class=num>${r.n}</td><td class=num>${pct(r.refusal)}</td><td class=num>${pct(r.abstain)}</td><td class=num>${pct(r.for)}</td><td class=num>${pct(r.against)}</td></tr>`).join("") + "</table>";
    for (const metric of ["agreement", "correlation"]){
      const col = metric === "agreement" ? agreeColor : corrColor;
      h += `<h3>${metric === "agreement" ? "Agreement (1 - mean |model - group| / 2)" : "Correlation with each group"}</h3><table><tr><th>model</th><th>variant</th>${s.groups.map(g => `<th>${esc(g)}</th>`).join("")}</tr>`;
      if (metric === "agreement") h += `<tr><td><i>always for</i></td><td class=muted>reference</td>${s.groups.map(g => `<td class=num style="${col(s.baseline[g])}">${s.baseline[g].toFixed(2)}</td>`).join("")}</tr>`;
      h += s.rows.map(r => `<tr><td>${esc(shortModel(r.model))}</td><td>${esc(r.variant)}</td>${s.groups.map(g => { const v = r[metric][g];
        return `<td class=num style="${col(v)}">${v === null ? "-" : v.toFixed(2)}</td>`; }).join("")}</tr>`).join("") + "</table>";
    }
  }
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
  renderList();
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
