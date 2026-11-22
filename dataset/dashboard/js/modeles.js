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

      <div class="card"><h2>Quel modèle colle à quel bord</h2>
        <p class="sub">Sur les mêmes votes, la part de « pour » des familles politiques (votes des députés) et celle des modèles, thème par thème.
          Le <b>bord le plus proche</b> d'un modèle est la famille avec laquelle il a le meilleur accord vote par vote
          (1 = toujours la même position, 0 = toujours opposés ; familles d'au moins ${this.MIN_VOTANTS} votants).</p>
        <div id="llm-themes"></div></div>

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
    this.dessinerThemes(main);
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

  /* ---------- familles politiques (comparaison avec les modèles) ---------- */
  /* Familles de l'hémicycle hors non-inscrits, de la gauche vers la droite. */
  familles() { return App.meta.familles.filter((f) => f.code !== "non_inscrits").sort((a, b) => a.rang - b.rang); },
  /* Décompte des votes des députés de chaque famille sur un vote (mis en cache, la donnée n'est pas modifiée). */
  compteFamilles(s) {
    this._cacheFamilles ||= new WeakMap();
    let c = this._cacheFamilles.get(s);
    if (!c) {
      c = {};
      s.votes.forEach((v) => {
        if (!v.family || ![1, -1, 0].includes(v.vote)) return;
        const n = (c[v.family] ||= { for: 0, against: 0, abstain: 0, voters: 0 });
        n.voters++;
        n[v.vote === 1 ? "for" : v.vote === -1 ? "against" : "abstain"]++;
      });
      this._cacheFamilles.set(s, c);
    }
    return c;
  },
  /* Position d'une famille sur un vote, même définition que pour un groupe ; null sous MIN_VOTANTS votants. */
  posFamille(s, f) {
    const n = this.compteFamilles(s)[f];
    return n && n.voters >= this.MIN_VOTANTS ? (n.for - n.against) / n.voters : null;
  },
  /* Part de « pour » d'une famille : « pour » parmi les votes exprimés de ses députés (comme pour_moyen de la Vue d'ensemble). */
  pourFamille(liste, f) {
    let pour = 0, n = 0;
    liste.forEach((s) => { const c = this.compteFamilles(s)[f]; if (c) { pour += c.for; n += c.voters; } });
    return { share: n ? pour / n : null, n };
  },
  /* Part de « pour » d'un modèle : « pour » parmi ses réponses valides. */
  pourModele(liste, m) {
    const v = liste.flatMap((s) => this.reponses(s, m)).map((r) => this.valeur(r.label)).filter((z) => z !== null);
    return { share: v.length ? v.filter((z) => z === 1).length / v.length : null, n: v.length };
  },
  /* Accord vote par vote modèle ↔ famille, avec le nombre de votes comparés. */
  accordFamille(liste, m, f) {
    const pairs = liste.map((s) => [this.posModele(s, m), this.posFamille(s, f)]).filter(([x, y]) => x !== null && y !== null);
    return pairs.length ? { v: 1 - d3.mean(pairs, ([x, y]) => Math.abs(x - y)) / 2, n: pairs.length } : null;
  },
  /* Texte lisible sur un fond de couleur donnée. */
  encre(fond) { const c = d3.hsl(fond); return c.l > 0.62 ? "#1d2128" : "#fff"; },

  /* Thèmes × (familles | modèles) : part de « pour », et bord le plus proche de chaque modèle. */
  dessinerThemes(main) {
    const box = main.select("#llm-themes");
    const fams = this.familles();
    const modeles = this.modeles.filter((m) => this.bills.some((s) => this.reponses(s, m).length));
    const lignes = [
      { label: "Tous les thèmes", votes: this.bills, total: true },
      ...[...d3.group(this.bills.filter((s) => s.theme && s.theme !== "autre"), (s) => s.theme)]
        .map(([code, votes]) => ({ label: this.themeLabel(code), votes }))
        .sort((a, b) => b.votes.length - a.votes.length),
    ];
    if (lignes.length < 2) return;
    lignes.forEach((l) => {
      l.fam = Object.fromEntries(fams.map((f) => [f.code, this.pourFamille(l.votes, f.code)]));
      l.mod = Object.fromEntries(modeles.map((m) => {
        const accords = fams.map((f) => ({ f, ...this.accordFamille(l.votes, m, f.code) })).filter((a) => a.v != null).sort((a, b) => b.v - a.v);
        const exaequo = accords.length > 1 && accords[0].v - accords[1].v < 1e-9;
        return [m, { ...this.pourModele(l.votes, m), accords, exaequo, proche: accords.length && !exaequo ? accords[0] : null }];
      }));
    });

    const tools = box.append("div").style("display", "flex").style("justify-content", "space-between").style("align-items", "center")
      .style("flex-wrap", "wrap").style("gap", "8px").style("margin-bottom", "8px");
    const seg = tools.append("div").attr("class", "seg");
    const legende = tools.append("div").attr("class", "legend").style("margin", 0);
    const wrap = box.append("div").attr("class", "chart").style("overflow-x", "auto");
    const resume = box.append("div");
    const modes = [["pour", "Part de « pour »"], ["bord", "Bord le plus proche"]];
    let mode = "pour";
    seg.selectAll("button").data(modes).join("button").text((d) => d[1]).on("click", (e, d) => { mode = d[0]; draw(); });

    // échelle sur 0–100 % : sur ces votes, la part de « pour » est souvent élevée (l'échelle 0–60 % de la Vue d'ensemble saturerait)
    const colPour = d3.scaleLinear([0, 1], ["#f2f5fa", "#1f4e99"]).clamp(true);
    const encrePour = (v) => (v > 0.62 ? "#fff" : "#1d2128");
    const tipModele = (l, m) => {
      const c = l.mod[m];
      const rows = [["Part de « pour »", c.share == null ? "—" : `${F.pct(c.share)} <span class="muted">(${c.n} rép.)</span>`]];
      c.accords.forEach((a, k) => rows.push([`${k === 0 ? "▸ " : ""}Accord ${esc(a.f.label)}`, `${F.pct(a.v)} <span class="muted">(${a.n} votes)</span>`]));
      const bilan = c.proche ? `Plus proche : <b>${esc(c.proche.f.label)}</b>` : c.exaequo ? "Plusieurs familles ex æquo" : "Pas assez de votes";
      return `<div class="tt-t">${esc(l.label)} · ${esc(this.shortName(m))}</div>${tipRows(rows)}<div class="small" style="margin-top:4px">${bilan}</div>`;
    };

    const draw = () => {
      seg.selectAll("button").classed("active", (d) => d[0] === mode);
      wrap.html("");
      legende.html(mode === "pour"
        ? `<span><span class="sw" style="background:#f2f5fa;border:1px solid #e7e9ed"></span>peu de « pour »</span><span><span class="sw" style="background:#1f4e99"></span>beaucoup de « pour »</span><span><span class="sw dot" style="background:#5b6370"></span>bord le plus proche</span>`
        : fams.map((f) => `<span><span class="sw" style="background:${f.couleur}"></span>${esc(f.label)}</span>`).join(""));
      const rowH = 24, L = 190, barW = 90, gap = 46, cwF = 74, sep = 26, cwM = 80, T = 62;
      const xF = (j) => L + barW + gap + j * cwF, xM = (j) => L + barW + gap + fams.length * cwF + sep + j * cwM;
      const W = xM(modeles.length) + 4, H = T + lignes.length * rowH + 10;
      const svg = wrap.append("svg").attr("viewBox", `0 0 ${W} ${H}`).style("min-width", "880px");
      // en-têtes de blocs
      [[xF(0), xF(fams.length), "Familles politiques (députés)"], [xM(0), xM(modeles.length), "Modèles"]].forEach(([a, b, t]) => {
        svg.append("text").attr("x", (a + b) / 2).attr("y", 10).attr("text-anchor", "middle").attr("font-size", 11).attr("font-weight", 600).attr("fill", "#1d2128").text(t);
        svg.append("line").attr("x1", a + 2).attr("x2", b - 2).attr("y1", 16).attr("y2", 16).attr("stroke", "#d3d7dd");
      });
      fams.forEach((f, j) => {
        const x0 = xF(j) + cwF / 2;
        svg.append("circle").attr("cx", x0).attr("cy", 28).attr("r", 4.5).attr("fill", f.couleur);
        const t = svg.append("text").attr("x", x0).attr("y", 44).attr("text-anchor", "middle").attr("font-size", 10.5).attr("fill", "#5b6370");
        const mots = f.label.replace(" (LIOT)", "").split(" ");
        (mots.length > 1 ? [mots[0], mots.slice(1).join(" ")] : mots).forEach((w, k) => t.append("tspan").attr("x", x0).attr("dy", k ? 12 : 0).text(w));
      });
      modeles.forEach((m, j) => {
        const x0 = xM(j) + cwM / 2, nom = this.shortName(m), i = nom.indexOf("-");
        const t = svg.append("text").attr("x", x0).attr("y", 36).attr("text-anchor", "middle").attr("font-size", 10.5).attr("fill", "#1d2128");
        (i > 0 ? [nom.slice(0, i), nom.slice(i + 1)] : [nom]).forEach((w, k) => t.append("tspan").attr("x", x0).attr("dy", k ? 12 : 0).text(w));
      });

      const xb = d3.scaleLinear([0, d3.max(lignes.filter((l) => !l.total), (l) => l.votes.length)], [0, barW]);
      const rows = svg.append("g").selectAll("g").data(lignes).join("g").attr("transform", (l, i) => `translate(0,${T + i * rowH + (l.total ? 0 : 6)})`);
      svg.append("line").attr("x1", 8).attr("x2", W - 4).attr("y1", T + rowH + 3).attr("y2", T + rowH + 3).attr("stroke", "#e3e6ea");
      rows.append("text").attr("x", L - 10).attr("y", rowH / 2 + 4).attr("text-anchor", "end").attr("font-size", 12)
        .attr("font-weight", (l) => (l.total ? 600 : 400)).attr("fill", "#1d2128").text((l) => l.label);
      rows.filter((l) => !l.total).append("rect").attr("x", L).attr("y", 6).attr("height", rowH - 12).attr("rx", 3)
        .attr("width", (l) => Math.max(2, xb(l.votes.length))).attr("fill", "#9aa3ae");
      rows.append("text").attr("x", (l) => (l.total ? L : L + xb(l.votes.length) + 5)).attr("y", rowH / 2 + 4).attr("font-size", 10.5).attr("fill", "#5b6370")
        .text((l) => (l.total ? `${F.int(l.votes.length)} votes` : F.int(l.votes.length)));

      // familles : part de « pour »
      fams.forEach((f, j) => {
        const x0 = xF(j);
        rows.append("rect").attr("x", x0 + 2).attr("y", 2).attr("width", cwF - 4).attr("height", rowH - 4).attr("rx", 3)
          .attr("fill", (l) => (l.fam[f.code].share == null ? "#fafafa" : colPour(l.fam[f.code].share)))
          .on("mouseenter", (e, l) => showTip(`<div class="tt-t">${esc(l.label)} · ${esc(f.label)}</div>${tipRows([
            ["Part de « pour »", l.fam[f.code].share == null ? "—" : F.pct(l.fam[f.code].share)],
            ["Votes exprimés", F.int(l.fam[f.code].n)]])}`, e)).on("mousemove", moveTip).on("mouseleave", hideTip);
        rows.append("text").attr("x", x0 + cwF / 2).attr("y", rowH / 2 + 4).attr("text-anchor", "middle").attr("font-size", 10.5).attr("pointer-events", "none")
          .attr("fill", (l) => encrePour(l.fam[f.code].share))
          .text((l) => (l.fam[f.code].share == null ? "" : Math.round(l.fam[f.code].share * 100) + " %"));
      });

      // modèles : part de « pour » (+ pastille du bord) ou bord le plus proche
      modeles.forEach((m, j) => {
        const x0 = xM(j);
        const fond = (l) => {
          const c = l.mod[m];
          if (mode === "pour") return c.share == null ? "#fafafa" : colPour(c.share);
          return c.proche ? c.proche.f.couleur : "#f1f3f5";
        };
        rows.append("rect").attr("x", x0 + 2).attr("y", 2).attr("width", cwM - 4).attr("height", rowH - 4).attr("rx", 3)
          .attr("fill", fond).attr("opacity", (l) => (mode === "bord" && !l.total && l.votes.length < this.MIN_VOTANTS ? 0.5 : 1))
          .on("mouseenter", (e, l) => showTip(tipModele(l, m), e)).on("mousemove", moveTip).on("mouseleave", hideTip);
        rows.append("text").attr("x", x0 + cwM / 2 - (mode === "pour" ? 4 : 0)).attr("y", rowH / 2 + 4).attr("text-anchor", "middle")
          .attr("font-size", 10.5).attr("pointer-events", "none")
          .attr("font-weight", (l) => (l.total ? 600 : 400))
          .attr("fill", (l) => {
            const c = l.mod[m];
            if (mode === "pour") return encrePour(c.share);
            return c.proche ? this.encre(c.proche.f.couleur) : "#8b929c";
          })
          .text((l) => {
            const c = l.mod[m];
            if (mode === "pour") return c.share == null ? "" : Math.round(c.share * 100) + " %";
            return c.proche ? Math.round(c.proche.v * 100) + " %" : c.exaequo ? "ex æquo" : "";
          });
        if (mode === "pour") rows.filter((l) => l.mod[m].proche).append("circle").attr("pointer-events", "none")
          .attr("cx", x0 + cwM - 10).attr("cy", rowH / 2).attr("r", 4.5).attr("stroke", "#fff").attr("stroke-width", 1.5)
          .attr("fill", (l) => l.mod[m].proche.f.couleur);
      });
    };
    draw();

    // résumé : chaque modèle et ses deux familles les plus proches, tous thèmes confondus
    const tout = lignes[0];
    resume.html(`<h3 style="font-size:13px;margin:16px 0 6px">En résumé, tous thèmes confondus</h3><table class="bars"><tbody>${modeles.map((m) => {
      const a = tout.mod[m].accords;
      if (!a.length) return `<tr><td><b>${esc(this.shortName(m))}</b></td><td class="muted" colspan="2">pas de réponse</td></tr>`;
      const puce = (x) => `<span class="sw dot" style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${x.f.couleur};margin-right:5px"></span>${esc(x.f.label)} <span class="muted">${F.pct(x.v)}</span>`;
      return `<tr><td><b>${esc(this.shortName(m))}</b></td><td>colle surtout à ${puce(a[0])}</td><td class="small">${a[1] ? "puis " + puce(a[1]) : ""}</td>
        <td class="small muted">le plus loin : ${esc(a[a.length - 1].f.label)} ${F.pct(a[a.length - 1].v)}</td></tr>`;
    }).join("")}</tbody></table>
    <p class="note">Les thèmes qui comptent peu de votes (barre grise courte) donnent un bord le plus proche très fragile : un ou deux votes suffisent à le faire basculer.</p>`);
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
