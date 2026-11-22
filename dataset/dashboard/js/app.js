/* Hémicycle — noyau : données, routage, utilitaires partagés. */
d3.formatDefaultLocale({ decimal: ",", thousands: " ", grouping: [3], currency: ["", " €"] });

const F = {
  int: d3.format(",d"),
  pct: d3.format(".0%"),
  pct1: d3.format(".1%"),
  dec: d3.format(".2f"),
  date: (s) => s ? new Date(s + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "—",
  dateLong: (s) => s ? new Date(s + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : "—",
  mois: (s) => new Date(s + "-15T12:00:00").toLocaleDateString("fr-FR", { month: "short", year: "2-digit" }),
};

const VOTE = {
  p: { label: "Pour", color: "#009E73", badge: "b-pour" },
  c: { label: "Contre", color: "#D55E00", badge: "b-contre" },
  a: { label: "Abstention", color: "#E69F00", badge: "b-abst" },
  n: { label: "Non-votant", color: "#8b929c", badge: "b-nv" },
  " ": { label: "Absent", color: "#e3e6ea", badge: "b-nv" },
};

const OBJETS = {
  amendement: "Amendement", sous_amendement: "Sous-amendement", article: "Article", ensemble: "Ensemble du texte",
  motion_censure: "Motion de censure", motion_procedure: "Motion de procédure", partie_budget: "Partie du budget",
  procedure: "Procédure", declaration: "Déclaration du Gouvernement", autre: "Autre",
};

const App = {
  leg: 17,
  meta: null,
  cache: {},
  route: { tab: "general", a: null, b: null },

  async start() {
    this.meta = await getJSON("data/meta.json");
    this.renderLegSwitch();
    d3.selectAll("#tabs a").on("click", (e) => this.go(e.currentTarget.dataset.tab));
    window.addEventListener("hashchange", () => this.onHash());
    this.onHash();
  },

  /* #/17/scrutins/VTANR5L17V123 */
  onHash() {
    const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
    const leg = parseInt(parts[0], 10);
    if ([15, 16, 17].includes(leg)) { this.leg = leg; parts.shift(); }
    this.route = { tab: parts[0] || "general", a: parts[1] ? decodeURIComponent(parts[1]) : null, b: parts[2] ? decodeURIComponent(parts[2]) : null };
    this.render();
  },
  go(tab, a, b) {
    const target = "#/" + [this.leg, tab, a, b].filter((x) => x != null && x !== "").map(encodeURIComponent).join("/");
    if (location.hash === target) this.onHash(); else location.hash = target;
  },
  setLeg(leg) {
    this.leg = leg;
    this.go(this.route.tab);
  },
  renderLegSwitch() {
    const sw = d3.select("#leg-switch");
    sw.selectAll("button").data(this.meta.legislatures).join("button")
      .text((d) => ({ 15: "XVe · 2017-2022", 16: "XVIe · 2022-2024", 17: "XVIIe · depuis 2024" }[d.code] || d.label))
      .on("click", (e, d) => this.setLeg(d.code));
  },

  async render() {
    d3.selectAll("#tabs a").classed("active", function () { return this.dataset.tab === App.route.tab; });
    d3.selectAll("#leg-switch button").classed("active", (d) => d.code === this.leg);
    const main = d3.select("#main");
    main.html('<div class="loading">Chargement…</div>');
    hideTip();
    try {
      if (this.route.tab === "deputes") await Deputes.render(main, this.route);
      else if (this.route.tab === "scrutins") await Scrutins.render(main, this.route);
      else if (this.route.tab === "modeles") await Modeles.render(main);
      else if (this.route.tab === "analyse") await Analyse.render(main);
      else await General.render(main);
    } catch (err) {
      console.error(err);
      main.html(`<div class="empty">Erreur de chargement : ${esc(err.message)}.<br>Lancez l'app avec <code>python3 app/serve.py</code>.</div>`);
    }
    window.scrollTo(0, 0);
  },

  /* ---------- données ---------- */
  async load(kind, leg = this.leg) {
    const k = `${kind}_${leg}`;
    if (!this.cache[k]) this.cache[k] = getJSON(`data/${k}.json`);
    return this.cache[k];
  },
  async texte(uid) {
    const k = "t_" + uid;
    if (!this.cache[k]) this.cache[k] = getJSON(`data/textes/${uid}.json`);
    return this.cache[k];
  },
  async detail(uid) {
    const k = "d_" + uid;
    if (!this.cache[k]) this.cache[k] = getJSON(`data/details/${uid}.json`);
    return this.cache[k];
  },
  /* Données jointes d'une législature, avec index pratiques. */
  async bundle(leg = this.leg) {
    const k = "bundle_" + leg;
    if (this.cache[k]) return this.cache[k];
    const [gen, dep, scr, vot] = await Promise.all([this.load("general", leg), this.load("deputes", leg), this.load("scrutins", leg), this.load("votes", leg)]);
    const b = {
      leg, general: gen, deputes: dep.deputes, scrutins: scr.scrutins, matrice: vot.matrice,
      depIndex: new Map(dep.deputes.map((d, i) => [d.id, i])),
      scrIndex: new Map(scr.scrutins.map((s, i) => [s.uid, i])),
      groupes: new Map(this.meta.legislatures.find((l) => l.code === leg).groupes.map((g) => [g.sigle, g])),
    };
    this.cache[k] = b;
    return b;
  },

  /* ---------- groupes et familles ---------- */
  groupe(sigle, leg = this.leg) {
    const l = this.meta.legislatures.find((x) => x.code === leg);
    return (l && l.groupes.find((g) => g.sigle === sigle)) || { sigle, nom: sigle, couleur: "#a4a9b0", rang: 99, famille: null };
  },
  famille(code) {
    return this.meta.familles.find((f) => f.code === code) || { code, label: "—", couleur: "#a4a9b0", rang: 99 };
  },
  theme(code) {
    const t = this.meta.themes.find((x) => x.code === code);
    return t ? t.label : code;
  },
};

/* Groupe d'un député à une date donnée (périodes [sigle, début, fin]). */
function groupeALaDate(dep, date) {
  for (const [sig, deb, fin] of dep.groupes || []) {
    if ((!deb || deb <= date) && (!fin || date <= fin)) return sig;
  }
  return dep.groupe;
}
function enMandat(dep, date) {
  if (!dep.mandats) return null;
  return dep.mandats.some(([deb, fin]) => (!deb || deb <= date) && (!fin || date <= fin));
}

/* ---------- utilitaires ---------- */
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} (${r.status})`);
  return r.json();
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function chipGroupe(sigle, leg) {
  const g = App.groupe(sigle, leg);
  return `<span class="chip" title="${esc(g.nom)}"><span class="sw" style="background:${g.couleur}"></span>${esc(sigle)}</span>`;
}
function badgeVote(code) {
  const v = VOTE[code] || VOTE[" "];
  return `<span class="badge ${v.badge}">${v.label}</span>`;
}
function badgeResultat(r) {
  return r === "a" || (typeof r === "string" && r.startsWith("adopt"))
    ? '<span class="badge b-adopte">Adopté</span>' : '<span class="badge b-rejete">Rejeté</span>';
}
/* Sièges d'un groupe : effectif à la fin de la période, ou « dissous » s'il n'existe plus. */
function sieges(gr) {
  return gr.effectif_dernier ? String(gr.effectif_dernier) : `<span class="muted small">dissous</span>`;
}
function cellBar(v, color = "#5b6370", max = 1, fmt = F.pct) {
  if (v == null) return '<span class="muted">—</span>';
  const w = Math.max(0, Math.min(1, v / max)) * 100;
  return `<div class="cellbar"><div class="track"><div class="fill" style="width:${w}%;background:${color}"></div></div><span class="val">${fmt(v)}</span></div>`;
}
/* Infobulle partagée */
const tipEl = () => document.getElementById("tooltip");
function showTip(html, ev) {
  const t = tipEl();
  t.innerHTML = html;
  t.hidden = false;
  moveTip(ev);
}
function moveTip(ev) {
  const t = tipEl();
  if (t.hidden || !ev) return;
  const pad = 14, w = t.offsetWidth, h = t.offsetHeight;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + w > window.innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > window.innerHeight - 8) y = ev.clientY - h - pad;
  t.style.left = x + "px";
  t.style.top = y + "px";
}
function hideTip() { const t = tipEl(); if (t) t.hidden = true; }
function tipRows(rows) {
  return rows.map(([l, v]) => `<div class="tt-r"><span>${l}</span><b>${v}</b></div>`).join("");
}
function legendHTML(items, dot = false) {
  return `<div class="legend">${items.map((i) => `<span><span class="sw ${dot ? "dot" : ""}" style="background:${i.color}"></span>${esc(i.label)}</span>`).join("")}</div>`;
}
