/* Onglet « Modèles IA » : les réponses des modèles mises en regard des votes officiels de dataset_2.
   Données : data/llm_dataset2.json (fusion pure, voir timothe_code/export_dashboard.py).
   Les graphiques calculent des agrégats d'affichage à partir de ces données ; aucune donnée n'est réécrite.
   Définitions reprises du rapport de timothe_code/vote_pipeline.py (accord, position d'un modèle, seuil de 3 votants). */
const Modeles = {
  data: null,
  variante: null,
  scrutinId: null,
  tout: false,
  filtre: "",
  MIN_VOTANTS: 3,
  EXCLUS: ["NI"],
  LIBELLES: {
    neutre: "Neutre : pour, contre ou abstention",
    binaire: "Binaire : pour ou contre",
    oui_non: "Consigne « oui / non / abstention »",
    simulation: "Simulation de recherche",
  },

  async charger() {
    if (!this.data) this.data = await getJSON("data/llm_dataset2.json");
    return this.data;
  },

  /* ---------- valeurs ---------- */
  valeur(label) { return label === "for" ? 1 : label === "against" ? -1 : label === "abstain" ? 0 : null; },
  reponses(s, m) { return s.reponses_llm.filter((r) => r.model === m && r.variant === this.variante); },

  /* Position d'un modèle sur un vote : (pour - contre) / réponses valides ; null si aucune réponse valide. */
  posModele(s, m) {
    const v = this.reponses(s, m).map((r) => this.valeur(r.label)).filter((x) => x !== null);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  },
  /* Position officielle d'un groupe ; null si moins de MIN_VOTANTS votants. */
  posGroupe(s, g) {
    const p = s.group_positions[g];
    return p && p.voters >= this.MIN_VOTANTS && p.position != null ? p.position : null;
  },
  /* Accord (définition du rapport) : 1 - moyenne de |a - b| / 2 sur les votes où les deux positions sont connues. */
  accord(liste, a, b, pos) {
    const pairs = liste.map((s) => [pos(s, a), pos(s, b)]).filter(([x, y]) => x !== null && y !== null);
    if (!pairs.length) return null;
    return 1 - d3.mean(pairs, ([x, y]) => Math.abs(x - y)) / 2;
  },
  shortName(m) { return m.includes("/") ? m.split("/").pop() : m; },

  /* ---------- calculs d'affichage ---------- */
  /* Carte : ACP des acteurs (modèles + groupes) sur les votes ; deux premiers axes par itérations de puissance. */
  acp2(matrice) {
    const n = matrice.length, m = matrice[0].length;
    const X = matrice.map((r) => r.slice());
    for (let j = 0; j < m; j++) {
      const mu = d3.mean(X, (r) => r[j]);
      X.forEach((r) => { r[j] -= mu; });
    }
    const G = X.map((a) => X.map((b) => d3.sum(a.map((v, j) => v * b[j]))));
    const total = d3.sum(G.map((r, i) => r[i])) || 1;
    let M = G.map((r) => r.slice());
    const axes = [];
    for (let k = 0; k < 2; k++) {
      let v = d3.range(n).map((i) => Math.sin(i + 1.3 + k));
      let lambda = 0;
      for (let it = 0; it < 400; it++) {
        const w = M.map((r) => d3.sum(r.map((x, j) => x * v[j])));
        const norme = Math.sqrt(d3.sum(w.map((x) => x * x))) || 1;
        v = w.map((x) => x / norme);
        lambda = norme;
      }
      axes.push({ v, lambda });
      M = M.map((r, i) => r.map((x, j) => x - lambda * v[i] * v[j]));
    }
    return {
      coords: d3.range(n).map((i) => ({ x: axes[0].v[i] * Math.sqrt(axes[0].lambda), y: axes[1].v[i] * Math.sqrt(axes[1].lambda) })),
      part: axes.map((a) => a.lambda / total),
    };
  },

  /* Scrutins de la variante affichée, ceux qui ont au moins une réponse. */
  votesAvecReponses(d) { return d.scrutins.filter((s) => s.reponses_llm.some((r) => r.variant === this.variante)); },
  modelesDe(d) { return [...new Set(d.scrutins.flatMap((s) => s.reponses_llm.map((r) => r.model)))]; },
  variantesDe(d) { return [...new Set(d.scrutins.flatMap((s) => s.reponses_llm.map((r) => r.variant)))]; },
  groupesDe(d) {
    const set = new Set();
    d.scrutins.forEach((s) => Object.keys(s.group_positions).forEach((g) => { if (!this.EXCLUS.includes(g)) set.add(g); }));
    return [...set].sort((a, b) => App.groupe(a, 17).rang - App.groupe(b, 17).rang);
  },

  /* ---------- rendu ---------- */
  async render(main) {
    let d;
    try {
      d = await this.charger();
    } catch (err) {
      main.html(`<div class="empty">Données des modèles introuvables.<br>Lancez <code>python3 timothe_code/export_dashboard.py</code>.</div>`);
      return;
    }
    this.modeles = this.modelesDe(d);
    this.groupes = this.groupesDe(d);
    const variantes = this.variantesDe(d);
    if (!this.variante || !variantes.includes(this.variante)) this.variante = variantes[0] || null;
    if (!this.modeles.length) {
      main.html(`<div class="empty">Aucune réponse de modèle pour l'instant.</div>`);
      return;
    }
    this.bills = this.votesAvecReponses(d);
    if (!this.bills.find((s) => s.id === this.scrutinId)) this.scrutinId = this.bills[0] ? this.bills[0].id : null;

    /* Acteurs : modèles puis groupes. */
    this.acteurs = [...this.modeles.map((m) => ({ id: m, modele: true })), ...this.groupes.map((g) => ({ id: g, modele: false }))];
    this.pos = (s, a) => (a.modele ? this.posModele(s, a.id) : this.posGroupe(s, a.id));

    const valides = this.modeles.flatMap((m) => this.bills.flatMap((s) => this.reponses(s, m)));
    const avecTexte = valides.filter((r) => r.label !== null).length;
    const oui = valides.filter((r) => r.label === "for" || r.label === "against");
    const coherents = oui.filter((r) => {
      const s = this.bills.find((b) => b.id === r.id);
      return s && (r.label === "for") === Boolean(s.result.adopted);
    }).length;

    const boutonsVariantes = variantes.map((v) =>
      `<button data-v="${esc(v)}" class="${v === this.variante ? "active" : ""}">${esc(this.LIBELLES[v] || v)}</button>`).join("");
    const optionsScrutins = this.bills.map((s) =>
      `<option value="${esc(s.id)}" ${s.id === this.scrutinId ? "selected" : ""}>${esc(F.date(s.date))} · ${esc((s.text_content.title || "").slice(0, 90))}</option>`).join("");

    main.html(`
      <div class="card">
        <h2>Les modèles face aux votes officiels</h2>
        <p class="sub">${this.bills.length} votes divisifs de la XVIIe législature avec réponses de modèles (dataset_2). Chaque modèle reçoit le titre et le texte voté,
          puis répond pour, contre ou abstention. Avec si peu de votes, un écart de quelques points n'est pas significatif.</p>
        <div class="seg" id="llm-variantes">${boutonsVariantes}</div>
        <div class="kpis" style="margin-top:14px">
          <div class="kpi"><div class="v">${F.int(d.scrutins.length)}</div><div class="l">Votes officiels</div><div class="h">dataset_2, XVIIe législature</div></div>
          <div class="kpi"><div class="v">${F.int(this.bills.length)}</div><div class="l">Votes avec réponses</div><div class="h">variante « ${esc(this.variante)} »</div></div>
          <div class="kpi"><div class="v">${this.modeles.length}</div><div class="l">Modèles</div><div class="h">${this.modeles.map((m) => esc(this.shortName(m))).join(", ")}</div></div>
          <div class="kpi"><div class="v">${valides.length ? F.pct(avecTexte / valides.length) : "—"}</div><div class="l">Réponses exploitables</div><div class="h">${F.int(avecTexte)} sur ${F.int(valides.length)}</div></div>
          <div class="kpi"><div class="v">${oui.length ? F.pct(coherents / oui.length) : "—"}</div><div class="l">Accord avec le résultat</div><div class="h">pour ou contre seulement, ${F.int(oui.length)} réponses</div></div>
        </div>
      </div>

      <div class="card"><h2>Le rythme des réponses</h2>
        <p class="sub">Part des réponses « pour » par mois de vote, pour chaque modèle.</p>
        <div id="llm-rythme" class="chart"></div></div>

      <div class="card"><h2>La carte politique</h2>
        <p class="sub">Chaque point est un acteur (modèle ou groupe), placé d'après sa position sur l'ensemble des votes :
          deux acteurs proches votent pareil. Les positions manquantes comptent comme neutres.</p>
        <div id="llm-carte" class="chart" style="max-width:760px;margin:0 auto"></div></div>

      <div class="card"><h2>Qui vote avec qui</h2>
        <p class="sub">Accord entre chaque paire d'acteurs : 1 = toujours la même position, 0 = toujours opposés.</p>
        <div id="llm-matrice" class="chart" style="overflow-x:auto"></div></div>

      <div class="card"><h2>Accord avec chaque groupe</h2>
        <p class="sub">Part des votes où la réponse du modèle est alignée sur la position du groupe (au moins ${this.MIN_VOTANTS} votants ; NI exclu).</p>
        <div id="llm-groupes"></div></div>

      <div class="card"><h2>Qui s'intéresse à quoi</h2>
        <p class="sub">Part des réponses « pour » par thème. Le nombre de réponses figure dans l'infobulle.</p>
        <div id="llm-themes" class="chart" style="overflow-x:auto"></div></div>

      <div class="card"><h2>Un vote, vu par chacun</h2>
        <p class="sub">Hémicycle officiel du vote (les députés qui ont voté) et réponses des modèles.</p>
        <select id="llm-scrutin" style="max-width:100%;margin-bottom:12px">${optionsScrutins}</select>
        <div id="llm-hemi" class="chart" style="max-width:760px;margin:0 auto"></div>
        <div id="llm-detail"></div></div>

      <div class="card"><h2>Données brutes</h2>
        <p class="sub">Chaque vote, son résultat officiel et la réponse de chaque modèle, telles que fusionnées.</p>
        <div class="table-wrap"><div id="llm-table"></div></div></div>`);

    this.dessinerRythme(main, d);
    this.dessinerCarte(main);
    this.dessinerMatrice(main);
    this.dessinerGroupes(main);
    this.dessinerThemes(main, d);
    await this.dessinerVote(main, d);
    this.dessinerTable(main);

    main.selectAll("#llm-variantes button").on("click", (e) => { this.variante = e.currentTarget.dataset.v; this.render(main); });
    main.select("#llm-scrutin").on("change", (e) => { this.scrutinId = e.target.value; this.dessinerVote(main, d); });
  },

  /* Le rythme : part des « pour » par mois, une ligne par modèle. */
  dessinerRythme(main, d) {
    const mois = [...new Set(this.bills.map((s) => s.date.slice(0, 7)))].sort();
    if (!mois.length) return;
    const W = 760, H = 300, mg = { t: 16, r: 110, b: 36, l: 44 };
    const x = d3.scalePoint().domain(mois).range([mg.l, W - mg.r]).padding(0.3);
    const y = d3.scaleLinear().domain([0, 1]).range([H - mg.b, mg.t]);
    const couleur = d3.scaleOrdinal(d3.schemeTableau10).domain(this.modeles);
    const svg = main.select("#llm-rythme").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    svg.append("g").attr("class", "grid-line").selectAll("line").data([0, 0.25, 0.5, 0.75, 1]).join("line")
      .attr("x1", mg.l).attr("x2", W - mg.r).attr("y1", (t) => y(t)).attr("y2", (t) => y(t));
    svg.append("g").selectAll("text").data([0, 0.5, 1]).join("text").attr("x", mg.l - 6).attr("y", (t) => y(t) + 4)
      .attr("text-anchor", "end").attr("font-size", 11).attr("fill", "#5b6370").text((t) => F.pct(t));
    svg.append("g").selectAll("text").data(mois).join("text").attr("x", (m) => x(m)).attr("y", H - 12)
      .attr("text-anchor", "middle").attr("font-size", 11).attr("fill", "#5b6370").text((m) => F.mois(m));
    this.modeles.forEach((m) => {
      const pts = mois.map((mo) => {
        const v = this.bills.filter((s) => s.date.slice(0, 7) === mo).flatMap((s) => this.reponses(s, m))
          .map((r) => this.valeur(r.label)).filter((z) => z !== null);
        return v.length ? { mo, share: v.filter((z) => z === 1).length / v.length, n: v.length } : null;
      }).filter(Boolean);
      if (!pts.length) return;
      const line = d3.line().x((p) => x(p.mo)).y((p) => y(p.share));
      svg.append("path").attr("d", line(pts)).attr("fill", "none").attr("stroke", couleur(m)).attr("stroke-width", 2);
      svg.append("g").selectAll("circle").data(pts).join("circle").attr("cx", (p) => x(p.mo)).attr("cy", (p) => y(p.share))
        .attr("r", 4).attr("fill", couleur(m))
        .on("mouseenter", (e, p) => showTip(tipRows([[esc(m), F.pct(p.share)], ["Réponses", p.n], ["Mois", F.mois(p.mo)]]), e))
        .on("mousemove", moveTip).on("mouseleave", hideTip);
      const last = pts[pts.length - 1];
      svg.append("text").attr("x", x(last.mo) + 8).attr("y", y(last.share) + 4).attr("font-size", 11).attr("fill", couleur(m)).text(this.shortName(m));
    });
    main.select("#llm-rythme").insert("div", "svg").html(legendHTML(this.modeles.map((m) => ({ label: this.shortName(m), color: couleur(m) }))));
  },

  /* La carte : ACP des acteurs. */
  dessinerCarte(main) {
    const matrice = this.acteurs.map((a) => this.bills.map((s) => { const p = this.pos(s, a); return p === null ? 0 : p; }));
    if (matrice.length < 2 || !this.bills.length) return;
    const { coords, part } = this.acp2(matrice);
    const W = 760, H = 460, mg = 40;
    const ext = (k) => d3.extent(coords, (c) => c[k]);
    const x = d3.scaleLinear().domain(ext("x")).nice().range([mg, W - mg]);
    const y = d3.scaleLinear().domain(ext("y")).nice().range([H - mg, mg]);
    const couleurModele = d3.scaleOrdinal(d3.schemeTableau10).domain(this.modeles);
    const couleur = (a) => (a.modele ? couleurModele(a.id) : App.groupe(a.id, 17).couleur || "#a4a9b0");
    const svg = main.select("#llm-carte").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    svg.append("line").attr("x1", mg).attr("x2", W - mg).attr("y1", y(0)).attr("y2", y(0)).attr("stroke", "#e3e6ea");
    svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", mg).attr("y2", H - mg).attr("stroke", "#e3e6ea");
    svg.append("text").attr("x", W / 2).attr("y", H - 8).attr("text-anchor", "middle").attr("font-size", 11).attr("fill", "#5b6370")
      .text(`axe 1 (${F.pct(part[0])} de la variance)`);
    this.acteurs.forEach((a, k) => {
      const c = coords[k];
      const g = svg.append("g").attr("transform", `translate(${x(c.x)},${y(c.y)})`)
        .on("mouseenter", (e) => showTip(tipRows([[esc(a.id), a.modele ? "modèle" : "groupe"]]), e))
        .on("mousemove", moveTip).on("mouseleave", hideTip);
      if (a.modele) g.append("path").attr("d", d3.symbol().type(d3.symbolDiamond).size(170)()).attr("fill", couleur(a)).attr("stroke", "#1d2128").attr("stroke-width", 0.8);
      else g.append("circle").attr("r", 7).attr("fill", couleur(a)).attr("stroke", "#fff").attr("stroke-width", 1.5);
      g.append("text").attr("x", 10).attr("y", 4).attr("font-size", 12).attr("fill", "#1d2128")
        .text(a.modele ? this.shortName(a.id) : a.id);
    });
    main.select("#llm-carte").insert("div", "svg").html(legendHTML([
      ...this.modeles.map((m) => ({ label: this.shortName(m) + " (modèle)", color: couleurModele(m) })),
      { label: "Groupe (couleur officielle)", color: "#a4a9b0" },
    ]));
  },

  /* Qui vote avec qui : matrice d'accord entre acteurs. */
  dessinerMatrice(main) {
    const acteurs = this.acteurs;
    const cw = 44, ch = 26, gauche = 110, haut = 84;
    const W = gauche + acteurs.length * cw + 10, H = haut + acteurs.length * ch + 10;
    const svg = main.select("#llm-matrice").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const couleur = d3.scaleSequential(d3.interpolateYlGnBu).domain([0, 1]);
    const etiquette = (a) => (a.modele ? this.shortName(a.id) : a.id);
    acteurs.forEach((a, j) => svg.append("text").attr("transform", `translate(${gauche + j * cw + cw / 2},${haut - 8}) rotate(-45)`)
      .attr("text-anchor", "start").attr("font-size", 11).attr("fill", "#5b6370").text(etiquette(a)));
    acteurs.forEach((a, i) => {
      svg.append("text").attr("x", gauche - 8).attr("y", haut + i * ch + ch / 2 + 4).attr("text-anchor", "end")
        .attr("font-size", 11).attr("fill", "#1d2128").text(etiquette(a));
      acteurs.forEach((b, j) => {
        const v = this.accord(this.bills, a, b, this.pos);
        svg.append("rect").attr("x", gauche + j * cw + 1).attr("y", haut + i * ch + 1).attr("width", cw - 2).attr("height", ch - 2)
          .attr("rx", 3).attr("fill", v === null ? "#f1f3f5" : couleur(v))
          .on("mouseenter", (e) => showTip(tipRows([[`${esc(etiquette(a))} ↔ ${esc(etiquette(b))}`, v === null ? "—" : F.pct(v)]]), e))
          .on("mousemove", moveTip).on("mouseleave", hideTip);
        if (v !== null) svg.append("text").attr("x", gauche + j * cw + cw / 2).attr("y", haut + i * ch + ch / 2 + 4)
          .attr("text-anchor", "middle").attr("font-size", 10).attr("pointer-events", "none")
          .attr("fill", v > 0.6 ? "#fff" : "#1d2128").text(Math.round(v * 100));
      });
    });
  },

  /* Accord avec chaque groupe, par modèle, avec la référence « toujours pour ». */
  dessinerGroupes(main) {
    const modeles = this.modeles, groupes = this.groupes;
    const toujoursPour = groupes.map((g) => this.accord(this.bills, { id: "ref", modele: true }, { id: g, modele: false },
      (s, a) => (a.modele ? 1 : this.posGroupe(s, a.id))));
    const lignes = modeles.map((m) => {
      const cellules = groupes.map((g) => this.accord(this.bills, { id: m, modele: true }, { id: g, modele: false }, this.pos));
      return `<tr><td><b>${esc(this.shortName(m))}</b></td>${cellules.map((v) => `<td>${v === null ? "—" : cellBar(v, "#5b6370", 1, F.pct)}</td>`).join("")}</tr>`;
    }).join("");
    main.select("#llm-groupes").html(`<div class="table-wrap"><table class="bars">
      <thead><tr><th>Modèle</th>${groupes.map((g) => `<th>${esc(g)}</th>`).join("")}</tr></thead>
      <tbody>${lignes}
        <tr class="muted"><td>Toujours « pour » (référence)</td>${toujoursPour.map((v) => `<td>${v === null ? "—" : F.pct(v)}</td>`).join("")}</tr>
      </tbody></table></div>`);
  },

  /* Thèmes × modèles : part des « pour ». */
  dessinerThemes(main, d) {
    const themes = [...new Set(this.bills.map((s) => s.theme).filter(Boolean))].sort();
    if (!themes.length) return;
    const cw = 92, ch = 26, gauche = 200, haut = 40;
    const W = gauche + this.modeles.length * cw + 10, H = haut + themes.length * ch + 10;
    const svg = main.select("#llm-themes").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const couleur = d3.scaleSequential(d3.interpolateYlGnBu).domain([0, 1]);
    this.modeles.forEach((m, j) => svg.append("text").attr("x", gauche + j * cw + cw / 2).attr("y", haut - 12)
      .attr("text-anchor", "middle").attr("font-size", 11).attr("fill", "#5b6370").text(this.shortName(m)));
    themes.forEach((t, i) => {
      svg.append("text").attr("x", gauche - 8).attr("y", haut + i * ch + ch / 2 + 4).attr("text-anchor", "end")
        .attr("font-size", 11).attr("fill", "#1d2128").text(this.themeLabel(t));
      this.modeles.forEach((m, j) => {
        const v = this.bills.filter((s) => s.theme === t).flatMap((s) => this.reponses(s, m)).map((r) => this.valeur(r.label)).filter((z) => z !== null);
        const share = v.length ? v.filter((z) => z === 1).length / v.length : null;
        svg.append("rect").attr("x", gauche + j * cw + 1).attr("y", haut + i * ch + 1).attr("width", cw - 2).attr("height", ch - 2)
          .attr("rx", 3).attr("fill", share === null ? "#f1f3f5" : couleur(share))
          .on("mouseenter", (e) => showTip(tipRows([[esc(this.themeLabel(t)), esc(this.shortName(m))], ["Pour", share === null ? "—" : F.pct(share)], ["Réponses", v.length]]), e))
          .on("mousemove", moveTip).on("mouseleave", hideTip);
        if (share !== null) svg.append("text").attr("x", gauche + j * cw + cw / 2).attr("y", haut + i * ch + ch / 2 + 4)
          .attr("text-anchor", "middle").attr("font-size", 10).attr("pointer-events", "none")
          .attr("fill", share > 0.6 ? "#fff" : "#1d2128").text(Math.round(share * 100) + " %");
      });
    });
  },
  themeLabel(code) { return App.theme(code); },

  /* Un vote : hémicycle officiel + positions des groupes + réponses des modèles. */
  async dessinerVote(main, d) {
    const s = this.bills.find((b) => b.id === this.scrutinId);
    const hemi = main.select("#llm-hemi");
    const detail = main.select("#llm-detail");
    hemi.html(""); detail.html("");
    if (!s) return;
    const dep = await App.load("deputes", 17);
    const place = new Map(dep.deputes.map((x) => [x.id, Number(x.place) || Infinity]));
    const code = (v) => (v === 1 ? "p" : v === -1 ? "c" : "a");
    const items = s.votes.map((v) => ({ ...v, code: code(v.vote) }))
      .sort((p, q) => (place.get(p.deputy_id) ?? Infinity) - (place.get(q.deputy_id) ?? Infinity));
    Hemicycle.draw(hemi, items, {
      width: 760, label: "Hémicycle du vote",
      fill: (it) => VOTE[it.code].color,
      tip: (it) => tipRows([["Député", esc(it.name)], ["Groupe", esc(it.group)], ["Vote", VOTE[it.code].label]]),
      center: [`${s.result.for} – ${s.result.against}`, "pour – contre"],
    });
    hemi.insert("div", "svg").html(legendHTML([{ label: "Pour", color: VOTE.p.color }, { label: "Contre", color: VOTE.c.color }, { label: "Abstention", color: VOTE.a.color }], true));

    const groupes = Object.entries(s.group_positions).filter(([g]) => !this.EXCLUS.includes(g));
    const lignesGroupes = groupes.map(([g, p]) => `<tr><td>${chipGroupe(g, 17)}</td><td>${cellBar(p.voters ? p.for / p.voters : null, VOTE.p.color, 1, F.pct)}</td>
      <td>${cellBar(p.voters ? p.against / p.voters : null, VOTE.c.color, 1, F.pct)}</td><td>${p.voters}</td></tr>`).join("");
    const lignesModeles = this.modeles.map((m) => {
      const rs = this.reponses(s, m);
      if (!rs.length) return `<tr><td>${esc(this.shortName(m))}</td><td colspan="2" class="muted">pas de réponse</td></tr>`;
      return rs.map((r) => `<tr><td>${esc(this.shortName(m))}</td><td>${this.pastille(r.label)}</td>
        <td class="small muted">${esc((r.text || r.error || "").replace(/\s+/g, " ").slice(0, 220))}</td></tr>`).join("");
    }).join("");
    detail.html(`
      <div class="grid" style="grid-template-columns:1fr 1fr;gap:18px;margin-top:14px">
        <div><h2 style="font-size:14px">Résultat officiel : ${badgeResultat(s.result.adopted ? "adopte" : "rejete")}</h2>
          <table class="bars"><thead><tr><th>Groupe</th><th>Pour</th><th>Contre</th><th>Votants</th></tr></thead><tbody>${lignesGroupes}</tbody></table></div>
        <div><h2 style="font-size:14px">Réponses des modèles</h2>
          <table class="bars"><thead><tr><th>Modèle</th><th>Réponse</th><th>Texte</th></tr></thead><tbody>${lignesModeles}</tbody></table></div>
      </div>`);
  },

  pastille(label) {
    const map = { for: ["Pour", "b-pour"], against: ["Contre", "b-contre"], abstain: ["Abstention", "b-abst"] };
    const [txt, cls] = map[label] || ["Sans réponse", "b-nv"];
    return `<span class="badge ${cls}">${txt}</span>`;
  },

  /* Données brutes : un vote par ligne, réponses de chaque modèle pour la variante affichée. */
  dessinerTable(main) {
    const cellule = (s, m) => {
      const rs = this.reponses(s, m);
      if (!rs.length) return '<td><span class="muted">—</span></td>';
      return "<td>" + rs.map((r) => `<div title="${esc((r.text || "").slice(0, 300))}">${this.pastille(r.label)}</div>`).join("") + "</td>";
    };
    const lignes = this.bills.map((s) => {
      const titre = s.text_content.title || s.vote_title || "";
      return `<tr><td><div>${esc(titre.charAt(0).toUpperCase() + titre.slice(1))}</div><span class="muted small">${F.date(s.date)} · ${esc(s.id)}</span></td>
        <td>${badgeResultat(s.result.adopted ? "adopte" : "rejete")}</td>${this.modeles.map((m) => cellule(s, m)).join("")}</tr>`;
    }).join("");
    main.select("#llm-table").html(`<table class="bars"><thead><tr><th>Texte</th><th>Résultat officiel</th>
      ${this.modeles.map((m) => `<th>${esc(this.shortName(m))}</th>`).join("")}</tr></thead><tbody>${lignes}</tbody></table>`);
  },
};
