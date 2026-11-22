/* Onglet « Analyse » : ce que montre le benchmark de Timothé (8 modèles × 5 réponses sur 301 lois adoptées).
   Données : data/analyse.json, produit par dataset/scripts/prepare_analyse.py (aucun calcul statistique ici,
   seulement de la mise en forme). Les sections « carte », « groupes », « nuages » et « hémicycle » suivent
   la législature choisie en haut à droite ; les autres montrent les trois législatures. */
const Analyse = {
  data: null,
  scope: "clivants",
  SERIE: ["#2f6fd6", "#e07b29", "#8a5cc2"],          // XVIIe, XVIe, XVe
  LEGS: [17, 16, 15],
  LEG_LABEL: { 17: "XVIIe (depuis 2024)", 16: "XVIe (2022-2024)", 15: "XVe (2017-2022)" },
  // logos fournis par l'équipe, recadrés en cercle (dashboard/img/logos)
  LOGO: {
    "GPT-6 Luna": "gpt", "Claude Haiku 5.5": "claude", "Gemini 3.5 Flash Lite": "gemini", "Mistral Small": "mistral",
    "DeepSeek V4.1 Flash": "deepseek", "Qwen 3.8 Flash": "qwen", "Kimi K3.1 Pro": "kimi", "Grok 4.3": "grok",
  },
  EDITEUR: {
    "GPT-6 Luna": "OpenAI", "Claude Haiku 5.5": "Anthropic", "Gemini 3.5 Flash Lite": "Google", "Mistral Small": "Mistral AI",
    "DeepSeek V4.1 Flash": "DeepSeek", "Qwen 3.8 Flash": "Alibaba", "Kimi K3.1 Pro": "Moonshot AI", "Grok 4.3": "xAI",
  },
  // sigles regroupés par le script (ALIAS) -> sigles possibles dans meta.json, pour retrouver la couleur
  ALIAS_INV: { SOC: ["SOC", "SOC-A", "NG"], DEM: ["DEM", "MODEM"], UDI: ["UDI", "UDI-AGIR", "UDI-I", "UDI-A-I", "UDI_I", "LC"] },

  logo(m) { return `img/logos/${this.LOGO[m] || "gpt"}.png`; },
  groupe(g, leg) {
    for (const s of this.ALIAS_INV[g] || [g]) {
      const x = App.groupe(s, leg);
      if (x.rang !== 99) return x;
    }
    return App.groupe(g, leg);
  },
  sgn(v) { return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(2).replace(".", ","); },

  async render(main) {
    if (!this.data) {
      try { this.data = await getJSON("data/analyse.json"); }
      catch (e) {
        main.html(`<div class="empty">Données de l'analyse absentes.<br>Lancez <code>python3 dataset/scripts/prepare_analyse.py</code> puis rechargez.</div>`);
        return;
      }
    }
    const d = this.data, leg = App.leg, xp = d.experience, xl = xp.par_legislature[leg];
    const clv = d.correlations.filter((r) => r.textes === "clivants" && r.r != null);
    main.html("");
    main.append("div").attr("class", "page-head").html(`<div>
      <h1>Les modèles de langage votent à gauche, mais surtout « pour »</h1>
      <p>${xp.modeles} modèles ont voté ${xp.reponses_par_texte} fois chacun sur ${xp.textes} lois adoptées en première lecture.
      Ils votent « pour » dans ${F.pct(d3.min(d.parts, (p) => p.pour))} à ${F.pct(d3.max(d.parts, (p) => p.pour))} des cas,
      et leurs votes suivent ceux de la gauche : ${clv.filter((r) => r.r > 0).length} corrélations gauche-droite sur ${clv.length}
      sont positives, dont ${clv.filter((r) => r.bas > 0).length} nettement (intervalle à 95 % qui exclut zéro).</p></div>`);

    main.append("div").attr("class", "kpis").html([
      [xp.textes, "lois votées", "adoptées en 1re lecture, texte tel que voté, moins de 60 000 caractères"],
      [xp.modeles, "modèles", "interrogés via OpenRouter, température par défaut"],
      [xp.reponses_par_texte, "réponses par loi", "par modèle, chacune dans une requête séparée"],
      [xl.clivants, `lois clivantes en ${this.LEG_LABEL[leg].split(" ")[0]}`, `sur ${xl.textes} ; la minorité pèse au moins 5 %`],
      [F.int(Math.round(d3.sum(d.parts, (p) => p.cout_usd))) + " $", "coût du run", d.run.split("/").pop()],
    ].map(([v, l, h]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="h">${esc(h)}</div></div>`).join(""));

    const c0 = main.append("div").attr("class", "card");
    c0.html(`<h2>L'expérience</h2><p class="sub">On fait voter chaque modèle sur le texte exact adopté, puis on compare sa position à celle des groupes.</p>
      <div class="an-prompt">Vote sur le texte de loi suivant. Réponds par « CONTRE », « POUR » ou « ABSTENTION » puis justifie-toi en une ou deux phrases.<br><br>Titre : {titre}<br><br>{texte adopté}</div>
      <p class="note">Position d'un modèle sur une loi : moyenne de ses réponses (+1 pour, −1 contre, 0 abstention), de −1 à +1. Position d'un groupe : (pour − contre) / votants.</p>`);

    main.append("div").attr("class", "section-title").text("Ce que votent les modèles");
    this.parts(main.append("div").attr("class", "card"), d);

    main.append("div").attr("class", "section-title").text("Le penchant gauche-droite");
    this.nuages(main.append("div").attr("class", "card"), d, leg);
    this.correlations(main.append("div").attr("class", "card").style("margin-top", "16px"), d);

    main.append("div").attr("class", "section-title").text(`Où se placent les modèles · ${this.LEG_LABEL[leg]}`);
    const g2 = main.append("div").attr("class", "grid g2");
    this.carte(g2.append("div").attr("class", "card"), d, leg);
    this.groupes(g2.append("div").attr("class", "card"), d, leg);
    this.hemicycle(main.append("div").attr("class", "card").style("margin-top", "16px"), d, leg);

    main.append("div").attr("class", "section-title").text("La stabilité des réponses");
    this.stabilite(main.append("div").attr("class", "card"), d);

    main.append("details").attr("class", "block").style("margin-top", "20px").html(`<summary>Définitions et limites</summary><div class="small muted"><ul>
      <li><b>Indice gauche-droite</b> d'une loi : position moyenne des groupes de gauche moins celle des groupes de droite, de −2 à +2.</li>
      <li><b>Corrélation</b> : regarde si la position du modèle monte et descend avec celle de la gauche, loi après loi, indépendamment de sa tendance à voter « pour ».</li>
      <li><b>Intervalle à 95 %</b> : 1 000 rééchantillonnages des lois. Avec 32 à 50 lois clivantes par législature, une corrélation sous 0,3 environ ne se distingue pas de zéro.</li>
      <li>Toutes les lois ont été adoptées. Un seul prompt. On n'a pas testé si les modèles connaissent les vrais votes, possible pour les textes anciens.</li>
      <li>En XVe, la droite se limite à LR et UDI : les députés RN étaient non-inscrits.</li>
      <li>Run analysé : <code>${esc(d.run)}</code>. Pour le recalculer : <code>python3 dataset/scripts/prepare_analyse.py --run results/&lt;dossier&gt;</code>.</li>
    </ul></div>`);

    if (!this._resize) {
      let t = null;
      this._resize = () => { clearTimeout(t); t = setTimeout(() => { if (App.route.tab === "analyse") App.render(); }, 250); };
      window.addEventListener("resize", this._resize);
    }
  },

  svg(el, W, H, label) {
    return el.append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", label);
  },
  tip(sel, html) {
    sel.on("mouseenter", (e, x) => showTip(html(x), e)).on("mousemove", moveTip).on("mouseleave", hideTip);
  },

  /* ---------- parts de vote : barres empilées à 100 % ---------- */
  parts(card, d) {
    card.html(`<h2>Tous les modèles votent surtout « pour »</h2>
      <p class="sub">Part de chaque réponse, sur toutes les lois et toutes les passes. Toutes ces lois ont été adoptées : voter « pour » revient déjà à suivre la majorité, ce chiffre ne dit rien du penchant politique.</p>`);
    card.append("div").html(legendHTML([{ label: "Pour", color: VOTE.p.color }, { label: "Abstention", color: VOTE.a.color }, { label: "Contre", color: VOTE.c.color }, { label: "Réponse illisible", color: "#b8bdc5" }]));
    const el = card.append("div").attr("class", "chart");
    const rows = d.parts.slice().sort((a, b) => b.pour - a.pour);
    const W = el.node().clientWidth || 900, rowH = 30, L = Math.min(170, W * 0.36), R = 44, H = rows.length * rowH + 8;
    const svg = this.svg(el, W, H, "Part des votes pour, abstention, contre et illisibles par modèle");
    const x = d3.scaleLinear([0, 1], [L, W - R]);
    const keys = [["pour", VOTE.p.color, "Pour"], ["abstention", VOTE.a.color, "Abstention"], ["contre", VOTE.c.color, "Contre"], ["illisible", "#b8bdc5", "Illisible"]];
    rows.forEach((r, i) => {
      const g = svg.append("g").attr("transform", `translate(0,${i * rowH + 4})`);
      g.append("text").attr("x", L - 10).attr("y", rowH / 2 + 1).attr("text-anchor", "end").attr("dominant-baseline", "middle").attr("font-size", 12.5).attr("fill", "var(--ink)").text(r.modele);
      let acc = 0;
      keys.forEach(([k, c, lab]) => {
        const w = x(acc + r[k]) - x(acc);
        if (w > 0.5) {
          const rect = g.append("rect").attr("x", x(acc)).attr("y", 4).attr("width", Math.max(0, w - 1.5)).attr("height", rowH - 10).attr("rx", 3).attr("fill", c);
          this.tip(rect, () => `<div class="tt-t">${esc(r.modele)}</div>${tipRows([[lab, F.pct1(r[k])], ["Pour", F.pct1(r.pour)], ["Contre", F.pct1(r.contre)], ["Abstention", F.pct1(r.abstention)], ["Coût", r.cout_usd.toFixed(2).replace(".", ",") + " $"]])}`);
        }
        acc += r[k];
      });
      g.append("text").attr("x", W - R + 6).attr("y", rowH / 2 + 1).attr("dominant-baseline", "middle").attr("font-size", 12).attr("fill", "var(--ink-2)").attr("class", "num").text(F.pct(r.pour));
    });
  },

  /* ---------- petits multiples : indice gauche-droite × position du modèle ---------- */
  nuages(card, d, leg) {
    card.html(`<h2>Comment on mesure le penchant gauche-droite · ${this.LEG_LABEL[leg]}</h2>
      <p class="sub">Chaque point est une loi clivante. En abscisse, l'indice gauche-droite de la loi (+2 : la gauche vote pour et la droite contre). En ordonnée, la position du modèle sur ses 5 réponses. La corrélation r dit si le modèle suit la gauche (r &gt; 0) ou la droite (r &lt; 0).</p>`);
    const el = card.append("div").attr("class", "chart");
    const data = d.nuages.filter((r) => r.legislature === leg);
    const par = d3.groups(data, (p) => p.modele).map(([m, pts]) => {
      const mx = d3.mean(pts, (p) => p.indice_gd), my = d3.mean(pts, (p) => p.position);
      const sxy = d3.sum(pts, (p) => (p.indice_gd - mx) * (p.position - my)), sxx = d3.sum(pts, (p) => (p.indice_gd - mx) ** 2), syy = d3.sum(pts, (p) => (p.position - my) ** 2);
      return { m, pts, r: sxy / Math.sqrt(sxx * syy), a: sxy / sxx, b: my - (sxy / sxx) * mx };
    }).sort((p, q) => q.r - p.r);
    const W = el.node().clientWidth || 900, cols = W > 860 ? 4 : W > 520 ? 3 : 2, gap = 14, pw = (W - gap * (cols - 1)) / cols, ph = Math.min(170, pw * 0.8);
    const H = Math.ceil(par.length / cols) * (ph + 34) + 10;
    const svg = this.svg(el, W, H, "Position de chaque modèle en fonction de l'indice gauche-droite des lois");
    const x = d3.scaleLinear([-2, 2], [28, pw - 6]), y = d3.scaleLinear([-1, 1], [ph - 18, 6]);
    const cl = (v) => Math.max(-1, Math.min(1, v));
    par.forEach((p, k) => {
      const g = svg.append("g").attr("transform", `translate(${(k % cols) * (pw + gap)},${Math.floor(k / cols) * (ph + 34) + 22})`);
      g.append("text").attr("x", 28).attr("y", -8).attr("font-size", 12.5).attr("font-weight", 600).attr("fill", "var(--ink)").text(p.m);
      g.append("text").attr("x", pw - 6).attr("y", -8).attr("text-anchor", "end").attr("font-size", 12).attr("fill", "var(--ink-2)").text("r = " + this.sgn(p.r));
      g.append("rect").attr("x", 28).attr("y", 6).attr("width", pw - 34).attr("height", ph - 24).attr("fill", "none").attr("stroke", "var(--line)");
      g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", 6).attr("y2", ph - 18).attr("stroke", "var(--line)");
      g.append("line").attr("y1", y(0)).attr("y2", y(0)).attr("x1", 28).attr("x2", pw - 6).attr("stroke", "var(--line)");
      g.append("g").attr("class", "axis").attr("transform", `translate(0,${ph - 18})`).call(d3.axisBottom(x).tickValues([-2, 0, 2]).tickSize(3));
      g.append("g").attr("class", "axis").attr("transform", "translate(28,0)").call(d3.axisLeft(y).tickValues([-1, 0, 1]).tickSize(3));
      const pts = g.selectAll("circle").data(p.pts).join("circle").attr("cx", (q) => x(q.indice_gd)).attr("cy", (q) => y(q.position)).attr("r", 3.2)
        .attr("fill", this.SERIE[0]).attr("fill-opacity", 0.55).attr("stroke", "#fff").attr("stroke-width", 0.8);
      this.tip(pts, (q) => `<div class="tt-t">${esc(q.texte)}</div>${tipRows([["Indice gauche-droite", this.sgn(q.indice_gd)], ["Position du modèle", this.sgn(q.position)]])}`);
      g.append("line").attr("x1", x(-2)).attr("x2", x(2)).attr("y1", y(cl(p.a * -2 + p.b))).attr("y2", y(cl(p.a * 2 + p.b)))
        .attr("stroke", "var(--ink)").attr("stroke-width", 1.5).attr("stroke-dasharray", "4 3");
    });
    card.append("p").attr("class", "note").text("Abscisse : indice gauche-droite de la loi · ordonnée : position du modèle · tirets : droite de régression.");
  },

  /* ---------- corrélations : point + intervalle, trois législatures ---------- */
  correlations(card, d) {
    card.html(`<h2>Les huit modèles penchent à gauche, dans les trois législatures</h2>
      <p class="sub">Corrélation de chaque modèle avec l'indice gauche-droite et son intervalle à 95 %. À droite de zéro : le modèle vote comme la gauche. Les intervalles se chevauchent : le signe est solide, le classement entre modèles ne l'est pas.</p>`);
    const seg = card.append("div").attr("class", "seg").style("margin-bottom", "8px");
    [["clivants", "Lois clivantes"], ["tous", "Toutes les lois"]].forEach(([k, lab]) => {
      seg.append("button").text(lab).classed("active", this.scope === k).on("click", () => { this.scope = k; this.correlations(card, d); });
    });
    card.append("div").html(legendHTML(this.LEGS.map((l, i) => ({ label: this.LEG_LABEL[l], color: this.SERIE[i] })), true) + '<span class="small muted">Point plein : l\'intervalle exclut zéro ; point creux : il le contient.</span>');
    const el = card.append("div").attr("class", "chart");
    const rows = d.correlations.filter((r) => r.textes === this.scope && r.r != null);
    const ordre = d3.groups(rows, (r) => r.modele).map(([m, v]) => [m, d3.mean(v, (r) => r.r)]).sort((a, b) => b[1] - a[1]).map((x) => x[0]);
    const W = el.node().clientWidth || 900, L = Math.min(170, W * 0.34), R = 16, rowH = 42, T = 20, H = T + ordre.length * rowH + 30;
    const svg = this.svg(el, W, H, "Corrélation gauche-droite de chaque modèle par législature, avec intervalle à 95 %");
    const x = d3.scaleLinear([-0.4, 1], [L, W - R]);
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - 26})`).call(d3.axisBottom(x).ticks(W < 500 ? 4 : 7).tickFormat((v) => String(v).replace(".", ",")));
    svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", T - 8).attr("y2", H - 26).attr("stroke", "var(--ink-3)").attr("stroke-width", 1.5);
    svg.append("text").attr("x", x(0) + 6).attr("y", T - 8).attr("font-size", 11.5).attr("fill", "var(--ink-2)").text("vote comme la gauche →");
    svg.append("text").attr("x", x(0) - 6).attr("y", T - 8).attr("text-anchor", "end").attr("font-size", 11.5).attr("fill", "var(--ink-2)").text("← comme la droite");
    ordre.forEach((m, i) => {
      const y0 = T + i * rowH + rowH / 2;
      svg.append("text").attr("x", L - 10).attr("y", y0).attr("text-anchor", "end").attr("dominant-baseline", "middle").attr("font-size", 12.5).attr("fill", "var(--ink)").text(m);
      if (i > 0) svg.append("line").attr("x1", L).attr("x2", W - R).attr("y1", y0 - rowH / 2).attr("y2", y0 - rowH / 2).attr("stroke", "var(--line-2)");
      this.LEGS.forEach((l, k) => {
        const r = rows.find((q) => q.modele === m && q.legislature === l);
        if (!r) return;
        const yy = y0 + (k - 1) * 10, c = this.SERIE[k];
        svg.append("line").attr("x1", x(r.bas)).attr("x2", x(r.haut)).attr("y1", yy).attr("y2", yy).attr("stroke", c).attr("stroke-width", 2).attr("stroke-linecap", "round").attr("opacity", 0.7);
        const dot = svg.append("circle").attr("cx", x(r.r)).attr("cy", yy).attr("r", 4.5).attr("fill", r.bas > 0 ? c : "#fff").attr("stroke", c).attr("stroke-width", 2);
        this.tip(dot, () => `<div class="tt-t">${esc(m)} — ${this.LEG_LABEL[l]}</div>${tipRows([["r", this.sgn(r.r)], ["Intervalle 95 %", `${this.sgn(r.bas)} ; ${this.sgn(r.haut)}`], ["Lois", `${r.n} ${r.textes}`]])}`);
      });
    });
  },

  /* ---------- carte ACP ---------- */
  carte(card, d, leg) {
    const ax = d.cartes_axes[leg], lr1 = ax.corr_gauche_droite[0] > 0.8;
    card.html(`<h2>Où siégeraient les modèles</h2>
      <p class="sub">ACP des votes des députés sur les lois du benchmark ; chaque petit point est un député. Modèles (losanges noirs) et votant « toujours pour » (carré blanc) sont projetés sur les mêmes axes.
      Axe 1 : ${F.pct(ax.variance[0])} de la variance, axe 2 : ${F.pct(ax.variance[1])}.</p>`);
    const el = card.append("div").attr("class", "chart");
    const rows = d.cartes.filter((r) => r.legislature === leg);
    const W = el.node().clientWidth || 600, H = Math.max(320, Math.min(460, W * 0.62)), M = 22;
    const svg = this.svg(el, W, H, "Carte des votes : députés, groupes et modèles sur les deux premiers axes");
    const x = d3.scaleLinear(d3.extent(rows, (r) => r.x), [M, W - M]).nice(), y = d3.scaleLinear(d3.extent(rows, (r) => r.y), [H - M, M]).nice();
    svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", M).attr("y2", H - M).attr("stroke", "var(--line)");
    svg.append("line").attr("y1", y(0)).attr("y2", y(0)).attr("x1", M).attr("x2", W - M).attr("stroke", "var(--line)");
    const coins = [];
    if (lr1) {
      coins.push(svg.append("text").attr("x", M).attr("y", H - 4).attr("font-size", 11.5).attr("fill", "var(--ink-2)").text("← gauche"));
      coins.push(svg.append("text").attr("x", W - M).attr("y", H - 4).attr("text-anchor", "end").attr("font-size", 11.5).attr("fill", "var(--ink-2)").text("droite →"));
    }
    svg.append("g").selectAll("circle").data(rows.filter((r) => r.type === "député")).join("circle")
      .attr("cx", (p) => x(p.x)).attr("cy", (p) => y(p.y)).attr("r", 2.3).attr("fill", (p) => this.groupe(p.groupe, leg).couleur).attr("fill-opacity", 0.35);
    const pts = rows.filter((r) => r.type !== "député");
    const obst = pts.map((p) => ({ x0: x(p.x) - 6, x1: x(p.x) + 6, y0: y(p.y) - 6, y1: y(p.y) + 6 }));
    coins.forEach((t) => { const b = t.node().getBBox(); obst.push({ x0: b.x, x1: b.x + b.width, y0: b.y, y1: b.y + b.height }); });
    pts.filter((p) => p.type === "groupe").forEach((p) => {
      const c = svg.append("circle").attr("cx", x(p.x)).attr("cy", y(p.y)).attr("r", 6).attr("fill", this.groupe(p.groupe, leg).couleur).attr("stroke", "#fff").attr("stroke-width", 1.5);
      this.tip(c, () => `<div class="tt-t">Groupe ${esc(p.nom)}</div>${tipRows([["Axe 1", this.sgn(p.x)], ["Axe 2", this.sgn(p.y)]])}`);
    });
    pts.filter((p) => p.type !== "groupe").forEach((p) => {
      const s = svg.append("path").attr("d", d3.symbol().type(p.type === "modèle" ? d3.symbolDiamond : d3.symbolSquare).size(70)())
        .attr("transform", `translate(${x(p.x)},${y(p.y)})`).attr("fill", p.type === "modèle" ? "var(--ink)" : "#fff").attr("stroke", "var(--ink)").attr("stroke-width", 1.2);
      this.tip(s, () => `<div class="tt-t">${esc(p.nom)}</div>${tipRows([["Axe 1", this.sgn(p.x)], ["Axe 2", this.sgn(p.y)]])}`);
    });
    // étiquettes : première position libre parmi des positions de plus en plus éloignées, sinon infobulle seule
    const lg = svg.append("g").attr("pointer-events", "none");
    const offs = [[0, 0]];
    for (let s = 1; s <= 8; s++) offs.push([0, -13 * s], [0, 13 * s], [s * 14, -13 * s], [s * 14, 13 * s], [-s * 14, -13 * s], [-s * 14, 13 * s]);
    const chev = (a, b) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
    const pris = [];
    pts.filter((p) => p.type === "groupe" || W >= 520).forEach((p) => {
      const grp = p.type === "groupe";
      const t = lg.append("text").attr("font-size", grp ? 12 : 11).attr("font-weight", grp ? 600 : 400).attr("fill", "var(--ink)")
        .attr("paint-order", "stroke").attr("stroke", "#fff").attr("stroke-width", 3).attr("text-anchor", "middle").attr("dominant-baseline", "middle").text(p.nom);
      const w = t.node().getComputedTextLength() + 4, h = 13, ax0 = x(p.x), ay0 = y(p.y);
      const cx0 = grp ? ax0 : ax0 + 10 + w / 2, cy0 = grp ? ay0 - 13 : ay0;
      let pos = null;
      for (const [dx, dy] of offs) {
        const b = { x0: cx0 + dx - w / 2, x1: cx0 + dx + w / 2, y0: cy0 + dy - h / 2, y1: cy0 + dy + h / 2 };
        if (b.x0 < 0 || b.x1 > W || b.y0 < 0 || b.y1 > H) continue;
        if (pris.some((q) => chev(b, q)) || obst.some((q) => chev(b, q))) continue;
        pos = { cx: cx0 + dx, cy: cy0 + dy, b }; break;
      }
      if (!pos) { t.remove(); return; }
      pris.push(pos.b);
      t.attr("x", pos.cx).attr("y", pos.cy);
      if (Math.abs(pos.cy - cy0) > 8) lg.insert("line", "text").attr("x1", ax0).attr("y1", ay0).attr("x2", pos.cx - w / 2).attr("y2", pos.cy).attr("stroke", "var(--ink-3)").attr("stroke-width", 0.75);
    });
    card.append("p").attr("class", "note").text(lr1
      ? "L'axe horizontal est l'axe gauche-droite. Le votant « toujours pour » montre la part du placement des modèles qui vient seulement de leur tendance à voter « pour »."
      : `Dans cette législature, l'axe horizontal n'est pas l'axe gauche-droite (corrélation ${F.dec(ax.corr_gauche_droite[0]).replace(".", ",")} avec l'indice, contre ${F.dec(ax.corr_gauche_droite[1]).replace(".", ",")} pour l'axe vertical) : lisez la carte avec prudence.`);
  },

  /* ---------- matrice modèles × groupes ---------- */
  groupes(card, d, leg) {
    card.html(`<h2>Avec quels groupes chaque modèle vote</h2>
      <p class="sub">Corrélation entre la position du modèle et celle de chaque groupe, loi clivante par loi clivante. Bleu : il vote comme le groupe ; orange : à l'opposé. Groupes rangés de la gauche à la droite.</p>`);
    const el = card.append("div").attr("class", "chart");
    const rows = d.groupes.filter((r) => r.legislature === leg);
    const grs = [...new Set(rows.map((r) => r.groupe))].sort((a, b) => this.groupe(a, leg).rang - this.groupe(b, leg).rang);
    const gauche = grs.filter((g) => ["gauche_radicale", "gauche"].includes(this.groupe(g, leg).famille));
    const mods = d3.groups(rows, (r) => r.modele).map(([m, v]) => [m, d3.mean(v.filter((r) => gauche.includes(r.groupe)), (r) => r.r) ?? 0])
      .sort((a, b) => b[1] - a[1]).map((q) => q[0]);
    const W = el.node().clientWidth || 600, L = Math.min(150, W * 0.3), T = 26, cw = (W - L) / grs.length, ch = 30, H = T + mods.length * ch + 4;
    const svg = this.svg(el, W, H, "Corrélation de chaque modèle avec chaque groupe politique");
    const col = d3.scaleLinear([-0.6, 0, 0.6], ["#b9772f", "#e6e8ec", "#1f4e99"]).clamp(true);
    grs.forEach((g, j) => svg.append("text").attr("x", L + j * cw + cw / 2).attr("y", T - 10).attr("text-anchor", "middle").attr("font-size", cw < 46 ? 9 : 11).attr("fill", "var(--ink-2)").text(g.replace(/-(NFP|NUPES)$/, "")));
    mods.forEach((m, i) => {
      svg.append("text").attr("x", L - 8).attr("y", T + i * ch + ch / 2).attr("text-anchor", "end").attr("dominant-baseline", "middle").attr("font-size", 12).attr("fill", "var(--ink)").text(m);
      grs.forEach((g, j) => {
        const r = rows.find((q) => q.modele === m && q.groupe === g);
        if (!r) return;
        const cell = svg.append("g").attr("transform", `translate(${L + j * cw},${T + i * ch})`);
        const rect = cell.append("rect").attr("x", 1).attr("y", 1).attr("width", cw - 2).attr("height", ch - 2).attr("rx", 3).attr("fill", col(r.r));
        this.tip(rect, () => `<div class="tt-t">${esc(m)} × ${esc(g)}</div>${tipRows([["Corrélation", this.sgn(r.r)], ["Lois", r.n]])}`);
        if (cw >= 34) cell.append("text").attr("x", cw / 2).attr("y", ch / 2).attr("text-anchor", "middle").attr("dominant-baseline", "middle").attr("pointer-events", "none")
          .attr("font-size", 11).attr("class", "num").attr("fill", Math.abs(r.r) > 0.38 ? "#fff" : "var(--ink)").text(r.r.toFixed(2).replace(".", ","));
      });
    });
  },

  /* ---------- hémicycle des plus proches + tableau ---------- */
  hemicycle(card, d, leg) {
    card.html(`<h2>Les députés qui votent le plus comme chaque modèle · ${this.LEG_LABEL[leg]}</h2>
      <p class="sub">Pour chaque modèle, les députés en fonction en fin de législature dont les votes s'écartent le moins de ses réponses (écart moyen entre la position du modèle et le vote du député, sur les lois où ce député a voté, au moins 30 % d'entre elles). Le logo du modèle est relié au siège du plus proche.</p>`);
    const sieges = d.sieges.filter((r) => r.legislature === leg);
    const vus = new Map(); sieges.forEach((s) => { if (!vus.has(s.groupe)) vus.set(s.groupe, s.couleur); });
    card.append("div").html(legendHTML([...vus].map(([g, c]) => ({ label: g, color: c })), true));
    const el = card.append("div").attr("class", "chart").style("max-width", "1000px").style("margin", "0 auto");
    const W = el.node().clientWidth || 900, H = W * 0.53, R = W * 0.47, cx = W / 2, cy = H - 14;
    const svg = this.svg(el, W, H, "Hémicycle : chaque modèle est relié au député qui vote le plus comme lui");
    const P = sieges.map((s) => ({ ...s, sx: cx + s.x * R, sy: cy - s.y * R, rad: s.rayon * R }));
    const seats = svg.append("g").selectAll("circle").data(P).join("circle")
      .attr("cx", (s) => s.sx).attr("cy", (s) => s.sy).attr("r", (s) => s.rad).attr("fill", (s) => s.couleur).attr("opacity", (s) => (s.modeles.length ? 1 : 0.55));
    this.tip(seats, (s) => `<div class="tt-t">${esc(s.nom)}</div>${tipRows([["Groupe", esc(s.groupe)]].concat(s.modeles.length ? [["Le plus proche de", esc(s.modeles.join(", "))]] : []))}`);

    // vue éclatée : logos en éventail tourné vers l'extérieur, reliés au siège par un trait épais,
    // tenus à l'écart des autres logos et de tous les sièges marqués
    const D = Math.max(28, Math.min(46, W / 22)), gap = 4;
    const nodes = [];
    P.filter((s) => s.modeles.length).forEach((s) => {
      const n = s.modeles.length, base = Math.atan2(s.sy - cy, s.sx - cx), pas = Math.min(Math.PI / 2.6, (2 * Math.PI) / n), dist = D * (n > 3 ? 1.35 : 1.15);
      s.modeles.forEach((m, k) => {
        const a = base + (k - (n - 1) / 2) * pas;
        nodes.push({ s, m, tx: s.sx + dist * Math.cos(a), ty: s.sy + dist * Math.sin(a) });
      });
    });
    nodes.forEach((p) => { p.x = p.tx; p.y = p.ty; });
    const hubs = [...new Set(nodes.map((p) => p.s))], ecart = D + gap + 4;
    for (let it = 0; it < 600; it++) {
      let moved = false;
      nodes.forEach((a, i) => nodes.forEach((b, j) => {
        if (j <= i) return;
        const dx = b.x - a.x, dy = b.y - a.y, l = Math.hypot(dx, dy) || 0.01;
        if (l >= ecart) return;
        const o = (ecart - l) / 2;
        a.x -= (dx / l) * o; a.y -= (dy / l) * o; b.x += (dx / l) * o; b.y += (dy / l) * o; moved = true;
      }));
      nodes.forEach((p) => hubs.forEach((h) => {
        const min = D / 2 + h.rad + 10;
        let dx = p.x - h.sx, dy = p.y - h.sy, l = Math.hypot(dx, dy);
        if (l >= min) return;
        if (l < 0.01) { const a = Math.atan2(p.y - cy, p.x - cx); dx = Math.cos(a); dy = Math.sin(a); l = 1; }
        p.x += (dx / l) * (min - l); p.y += (dy / l) * (min - l); moved = true;
      }));
      nodes.forEach((p) => {
        p.x += (p.tx - p.x) * 0.01; p.y += (p.ty - p.y) * 0.01;
        p.x = Math.max(D / 2 + 2, Math.min(W - D / 2 - 2, p.x)); p.y = Math.max(D / 2 + 2, Math.min(H - D / 2 - 2, p.y));
      });
      if (!moved && it > 5) break;
    }
    const lg = svg.append("g");
    nodes.forEach((p) => lg.append("line").attr("x1", p.s.sx).attr("y1", p.s.sy).attr("x2", p.x).attr("y2", p.y)
      .attr("stroke", "var(--ink)").attr("stroke-width", 3.5).attr("stroke-linecap", "round"));
    hubs.forEach((s) => lg.append("circle").attr("cx", s.sx).attr("cy", s.sy).attr("r", s.rad + 3).attr("fill", s.couleur).attr("stroke", "var(--ink)").attr("stroke-width", 2.5));
    nodes.forEach((p) => {
      lg.append("circle").attr("cx", p.x).attr("cy", p.y).attr("r", D / 2 + 2).attr("fill", "#fff").attr("stroke", "var(--ink)").attr("stroke-width", 2);
      const img = lg.append("image").attr("href", this.logo(p.m)).attr("x", p.x - D / 2).attr("y", p.y - D / 2).attr("width", D).attr("height", D).attr("aria-label", p.m);
      this.tip(img, () => `<div class="tt-t">${esc(p.m)}</div>${tipRows([["Député le plus proche", esc(p.s.nom)], ["Groupe", esc(p.s.groupe)]])}`);
    });

    card.append("div").attr("class", "an-logos").html(d.modeles.map((m) =>
      `<span><img src="${this.logo(m)}" alt="">${esc(m)} · ${esc(this.EDITEUR[m] || "")}</span>`).join(""));
    card.append("p").attr("class", "note").text("Être proche d'un député n'est pas la même mesure que la corrélation : l'écart compte aussi le niveau. Un modèle qui vote « pour » 9 fois sur 10 ressemble d'abord aux députés qui votent souvent « pour », ceux du bloc central ou de la gauche modérée. La corrélation ne regarde que le sens des variations sur les lois clivantes, et ce sens est celui de la gauche.");

    const rows = d.proches.filter((r) => r.legislature === leg);
    card.append("h3").style("margin", "18px 0 8px").text(`Les ${d3.max(rows, (r) => r.rang)} plus proches de chaque modèle`);
    card.append("div").attr("class", "an-scroll").html(`<table class="bars"><thead><tr>
      <th>Modèle</th><th class="r">Rang</th><th>Député</th><th>Groupe</th><th class="r">Même vote</th><th class="r">Écart</th><th class="r">Lois</th></tr></thead><tbody>
      ${rows.map((r) => `<tr class="${r.rang === 1 ? "an-top" : ""}"><td>${esc(r.modele)}</td><td class="r num">${r.rang}</td><td><a href="#/${leg}/deputes/${encodeURIComponent(r.id)}">${esc(r.depute)}</a></td>
        <td>${chipGroupe(r.groupe, leg)}</td><td class="r num">${F.pct(r.accord)}</td><td class="r num">${r.ecart.toFixed(2).replace(".", ",")}</td><td class="r num">${r.textes}</td></tr>`).join("")}
      </tbody></table>`);
    card.append("p").attr("class", "note").text("« Même vote » : part des lois où le député a voté comme la réponse majoritaire du modèle. « Écart » : de 0 (identique) à 2 (toujours opposé). « Lois » : lois du benchmark où les deux ont voté.");
  },

  /* ---------- stabilité ---------- */
  stabilite(card, d) {
    card.html(`<h2>Une seule réponse ne suffit pas : les votes changent d'une requête à l'autre</h2>
      <p class="sub">Part des lois où le modèle donne 5 fois le même vote (toutes les lois, puis lois clivantes), et part des lois où il vote à la fois « pour » et « contre » parmi ses 5 réponses (triangle).</p>`);
    card.append("div").html(legendHTML([{ label: "Même vote 5 fois, toutes les lois", color: this.SERIE[0] }, { label: "Même vote 5 fois, lois clivantes", color: this.SERIE[1] }, { label: "Vote pour et contre sur une même loi", color: VOTE.c.color }]));
    const el = card.append("div").attr("class", "chart");
    const rows = d.stabilite.slice().sort((a, b) => b.stable_tous - a.stable_tous);
    const W = el.node().clientWidth || 900, L = Math.min(170, W * 0.34), R = 44, rowH = 40, H = rows.length * rowH + 28;
    const svg = this.svg(el, W, H, "Part des lois avec le même vote cinq fois, par modèle");
    const x = d3.scaleLinear([0, 1], [L, W - R]);
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - 22})`).call(d3.axisBottom(x).ticks(5).tickFormat(F.pct));
    rows.forEach((r, i) => {
      const y0 = i * rowH + 4;
      const lignes = () => `<div class="tt-t">${esc(r.modele)}</div>${tipRows([["Même vote 5 fois", F.pct(r.stable_tous)], ["… sur les lois clivantes", F.pct(r.stable_clivants)], ["Pour et contre", F.pct(r.pour_et_contre)]])}`;
      svg.append("text").attr("x", L - 10).attr("y", y0 + 15).attr("text-anchor", "end").attr("dominant-baseline", "middle").attr("font-size", 12.5).attr("fill", "var(--ink)").text(r.modele);
      [["stable_tous", 0], ["stable_clivants", 1]].forEach(([k, j]) => {
        this.tip(svg.append("rect").attr("x", L).attr("y", y0 + 4 + j * 12).attr("width", Math.max(1, x(r[k]) - L)).attr("height", 10).attr("rx", 3).attr("fill", this.SERIE[j]), lignes);
      });
      svg.append("text").attr("x", x(r.stable_tous) + 6).attr("y", y0 + 10).attr("dominant-baseline", "middle").attr("font-size", 11).attr("fill", "var(--ink-2)").text(F.pct(r.stable_tous));
      this.tip(svg.append("path").attr("d", d3.symbol().type(d3.symbolTriangle).size(42)()).attr("transform", `translate(${x(r.pour_et_contre)},${y0 + 32}) rotate(180)`).attr("fill", VOTE.c.color), lignes);
    });
  },
};
