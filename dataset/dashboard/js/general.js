/* Onglet « Vue d'ensemble » */
const OBJ_CAT = [
  { key: "amend", label: "Amendements", color: "#3C6FB0", match: ["amendement", "sous_amendement"] },
  { key: "art", label: "Articles", color: "#9DBCE3", match: ["article"] },
  { key: "ens", label: "Ensemble d'un texte", color: "#1d2128", match: ["ensemble", "partie_budget"] },
  { key: "mot", label: "Motions", color: "#B07AA1", match: ["motion_censure", "motion_procedure"] },
  { key: "aut", label: "Procédure & autres", color: "#d3d7dd", match: ["procedure", "declaration", "autre"] },
];

const General = {
  async render(main) {
    const b = await App.bundle();
    const g = b.general;
    const leg = App.meta.legislatures.find((l) => l.code === b.leg);
    main.html("");
    main.append("div").attr("class", "page-head").html(`
      <div><h1>${leg.label}</h1>
      <p>Tous les scrutins publics de l'Assemblée nationale du ${F.dateLong(g.periode[0])} au ${F.dateLong(g.periode[1])} :
      qui vote, avec qui, sur quels sujets.</p></div>`);

    // ---- chiffres clés
    const adoptes = g.adoptes / g.n_scrutins;
    main.append("div").attr("class", "kpis").html([
      [F.int(g.n_scrutins), "scrutins publics", `${F.int(g.par_objet.amendement || 0)} sur des amendements`],
      [F.int(g.n_votes), "votes individuels", "pour, contre, abstention, non-votant"],
      [F.int(g.n_deputes), "députés ayant siégé", "remplaçants compris"],
      [F.pct(adoptes), "des scrutins adoptés", `${F.int(g.adoptes)} adoptés, ${F.int(g.n_scrutins - g.adoptes)} rejetés`],
      [F.pct(g.participation_moyenne), "participation moyenne", "les députés votent surtout sur leurs sujets"],
    ].map(([v, l, h]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="h">${h}</div></div>`).join(""));

    const r1 = main.append("div").attr("class", "grid g2");
    this.rythme(r1.append("div").attr("class", "card"), g);
    this.carte(r1.append("div").attr("class", "card"), b);

    main.append("div").attr("class", "section-title").text("Les groupes");
    const r2 = main.append("div").attr("class", "grid g2");
    this.accords(r2.append("div").attr("class", "card"), g, b.leg);
    this.tableGroupes(r2.append("div").attr("class", "card"), g, b.leg);

    main.append("div").attr("class", "section-title").text("Les sujets");
    this.themes(main.append("div").attr("class", "card"), g);

    main.append("div").attr("class", "section-title").text("Qui fait voter");
    const r3 = main.append("div").attr("class", "grid g2");
    this.initiative(r3.append("div").attr("class", "card"), g, b.leg);
    this.dossiers(r3.append("div").attr("class", "card"), g);
  },

  /* Scrutins par mois, empilés par objet */
  rythme(card, g) {
    card.html(`<h2>Le rythme des scrutins</h2><p class="sub">Nombre de scrutins publics par mois, selon l'objet du vote.</p>`);
    card.append("div").html(legendHTML(OBJ_CAT));
    const mois = Object.keys(g.par_mois);
    const data = mois.map((m) => {
      const o = { m };
      OBJ_CAT.forEach((c) => { o[c.key] = d3.sum(c.match, (k) => g.par_mois[m][k] || 0); });
      return o;
    });
    const W = 620, H = 260, M = { t: 8, r: 8, b: 26, l: 36 };
    const x = d3.scaleBand(mois, [M.l, W - M.r]).padding(0.18);
    const stack = d3.stack().keys(OBJ_CAT.map((c) => c.key))(data);
    const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d3.sum(OBJ_CAT, (c) => d[c.key]))]).nice().range([H - M.b, M.t]);
    const svg = card.append("div").attr("class", "chart").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    svg.append("g").attr("class", "grid-line").attr("transform", `translate(${M.l},0)`)
      .call(d3.axisLeft(y).ticks(4).tickSize(-(W - M.l - M.r)).tickFormat("")).call((s) => s.select(".domain").remove());
    svg.append("g").attr("class", "axis").attr("transform", `translate(${M.l},0)`).call(d3.axisLeft(y).ticks(4).tickSize(0).tickPadding(6))
      .call((s) => s.select(".domain").remove());
    const step = Math.ceil(mois.length / 9);
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - M.b})`)
      .call(d3.axisBottom(x).tickValues(mois.filter((_, i) => i % step === 0)).tickFormat(F.mois).tickSize(0).tickPadding(8));
    const colors = new Map(OBJ_CAT.map((c) => [c.key, c.color]));
    svg.append("g").selectAll("g").data(stack).join("g").attr("fill", (s) => colors.get(s.key))
      .selectAll("rect").data((s) => s.map((d) => ({ ...d, key: s.key }))).join("rect")
      .attr("x", (d) => x(d.data.m)).attr("width", x.bandwidth())
      .attr("y", (d) => y(d[1])).attr("height", (d) => Math.max(0, y(d[0]) - y(d[1]) - (d[1] - d[0] > 0 ? 1 : 0)));
    // zone de survol par mois
    svg.append("g").selectAll("rect").data(data).join("rect")
      .attr("x", (d) => x(d.m) - x.step() * x.paddingInner() / 2).attr("width", x.step()).attr("y", M.t).attr("height", H - M.b - M.t)
      .attr("fill", "transparent")
      .on("mouseenter", (e, d) => showTip(`<div class="tt-t">${new Date(d.m + "-15").toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}</div>` +
        tipRows(OBJ_CAT.map((c) => [c.label, F.int(d[c.key])]).concat([["Total", F.int(d3.sum(OBJ_CAT, (c) => d[c.key]))]])), e))
      .on("mousemove", moveTip).on("mouseleave", hideTip);
    const pic = data.reduce((a, d) => (d3.sum(OBJ_CAT, (c) => d[c.key]) > d3.sum(OBJ_CAT, (c) => a[c.key]) ? d : a), data[0]);
    card.append("p").attr("class", "note").text(`Les pics suivent l'examen des grands textes. Mois le plus chargé : ${new Date(pic.m + "-15").toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}, avec ${F.int(d3.sum(OBJ_CAT, (c) => pic[c.key]))} scrutins.`);
  },

  /* Carte politique (ACP des votes) */
  carte(card, b) {
    const g = b.general;
    const pts = b.deputes.filter((d) => d.x != null);
    card.html(`<h2>La carte politique</h2><p class="sub">Chaque point est un député, placé d'après l'ensemble de ses votes. Deux députés proches votent pareil.</p>`);
    card.append("div").html(legendHTML(g.ordre_groupes.map((s) => ({ label: s, color: App.groupe(s, b.leg).couleur })), true));
    const W = 620, H = 340, M = { t: 24, r: 10, b: 26, l: 10 };
    const x = d3.scaleLinear().domain(d3.extent(pts, (d) => d.x)).nice().range([M.l, W - M.r]);
    const y = d3.scaleLinear().domain(d3.extent(pts, (d) => d.y)).nice().range([H - M.b, M.t]);
    const svg = card.append("div").attr("class", "chart").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", M.t).attr("y2", H - M.b).attr("stroke", "#eef0f2");
    svg.append("line").attr("y1", y(0)).attr("y2", y(0)).attr("x1", M.l).attr("x2", W - M.r).attr("stroke", "#eef0f2");
    const v = g.acp_variance || [0, 0];
    svg.append("text").attr("x", W - M.r).attr("y", H - 6).attr("text-anchor", "end").attr("font-size", 11).attr("fill", "#8b929c")
      .text(`axe 1 → (${F.pct(v[0])} de la variance)`);
    svg.append("text").attr("x", x(0) + 6).attr("y", 12).attr("font-size", 11).attr("fill", "#8b929c").text(`↑ axe 2 (${F.pct(v[1])} de la variance)`);
    svg.append("g").selectAll("circle").data(pts).join("circle")
      .attr("cx", (d) => x(d.x)).attr("cy", (d) => y(d.y)).attr("r", 3.6)
      .attr("fill", (d) => App.groupe(d.groupe, b.leg).couleur).attr("fill-opacity", 0.85)
      .attr("stroke", "#fff").attr("stroke-width", 0.8).style("cursor", "pointer")
      .on("mouseenter", (e, d) => showTip(`<div class="tt-t">${esc(d.nom)}</div>${tipRows([["Groupe", d.groupe], ["Participation", d.participation != null ? F.pct(d.participation) : "—"], ["Vote avec son groupe", d.loyaute != null ? F.pct(d.loyaute) : "—"]])}`, e))
      .on("mousemove", moveTip).on("mouseleave", hideTip)
      .on("click", (e, d) => App.go("deputes", d.id));
    // étiquettes de groupe au barycentre
    const cent = d3.rollups(pts, (v) => ({ x: d3.median(v, (d) => d.x), y: d3.median(v, (d) => d.y), n: v.length }), (d) => d.groupe)
      .filter(([, c]) => c.n >= 8)
      .map(([s, c]) => ({ s: s.replace(/-(NUPES|NFP)$/, ""), px: x(c.x), py: y(c.y) - 9 }))
      .sort((a, c) => a.py - c.py);
    // évite les chevauchements d'étiquettes : décale vers le bas celles qui tombent sur une autre
    cent.forEach((a, k) => {
      for (let t = 0; t < k; t++) {
        const o = cent[t];
        if (Math.abs(a.px - o.px) < 7 * (a.s.length + o.s.length) / 2 + 6 && Math.abs(a.py - o.py) < 13) a.py = o.py + 13;
      }
    });
    svg.append("g").selectAll("text").data(cent).join("text")
      .attr("x", (c) => c.px).attr("y", (c) => c.py).attr("text-anchor", "middle")
      .attr("font-size", 11.5).attr("font-weight", 600).attr("fill", "#1d2128")
      .attr("paint-order", "stroke").attr("stroke", "#fff").attr("stroke-width", 3).attr("pointer-events", "none")
      .text((c) => c.s);
    const majorite = { 15: "LaREM, MoDem, Agir", 16: "Renaissance, MoDem, Horizons" }[b.leg];
    card.append("p").attr("class", "note").text(majorite
      ? `Sous la ${b.leg === 15 ? "XVe" : "XVIe"} législature, l'axe horizontal oppose d'abord la majorité présidentielle (${majorite}) aux oppositions ; le clivage gauche-droite se lit sur l'axe vertical, la gauche en haut.`
      : "L'axe horizontal range les députés de la gauche à la droite ; l'axe vertical sépare le bloc central et la droite républicaine des groupes plus contestataires.");
  },

  /* Matrice d'accord entre groupes */
  accords(card, g, leg) {
    const sig = g.ordre_groupes.filter((s) => s !== "NI");
    card.html(`<h2>Qui vote avec qui</h2><p class="sub">Part des scrutins où les deux groupes ont pris la même position majoritaire (pour, contre ou abstention).</p>`);
    const n = sig.length, cell = 38, L = 64, T = 26;
    const W = L + n * cell + 4, H = T + n * cell + 4;
    const col = d3.scaleLinear([0.2, 1], ["#f2f5fa", "#1f4e99"]).clamp(true);
    const svg = card.append("div").attr("class", "chart").style("max-width", "560px").append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    sig.forEach((s, i) => {
      svg.append("text").attr("x", L - 8).attr("y", T + i * cell + cell / 2 + 4).attr("text-anchor", "end").attr("font-size", 11).attr("fill", "#5b6370").text(s);
      svg.append("text").attr("x", L + i * cell + cell / 2).attr("y", T - 8).attr("text-anchor", "middle").attr("font-size", 10).attr("fill", "#5b6370").text(s.replace(/-.*/, ""));
    });
    const cells = [];
    sig.forEach((a, i) => sig.forEach((c, j) => cells.push({ a, c, i, j, v: g.accords_groupes[a]?.[c] })));
    const gc = svg.append("g").selectAll("g").data(cells).join("g").attr("transform", (d) => `translate(${L + d.j * cell},${T + d.i * cell})`);
    gc.append("rect").attr("width", cell - 2).attr("height", cell - 2).attr("rx", 3)
      .attr("fill", (d) => (d.v == null ? "#f7f8fa" : d.i === d.j ? "#f7f8fa" : col(d.v)))
      .on("mouseenter", (e, d) => d.i !== d.j && showTip(`<div class="tt-t">${d.a} × ${d.c}</div>${tipRows([["Même position", d.v != null ? F.pct(d.v) : "—"]])}`, e))
      .on("mousemove", moveTip).on("mouseleave", hideTip);
    gc.filter((d) => d.i !== d.j && d.v != null).append("text").attr("x", (cell - 2) / 2).attr("y", (cell - 2) / 2 + 4)
      .attr("text-anchor", "middle").attr("font-size", 10.5).attr("pointer-events", "none")
      .attr("fill", (d) => (d.v > 0.62 ? "#fff" : "#1d2128")).text((d) => Math.round(d.v * 100));
    // paire la plus proche entre blocs
    let best = null;
    cells.forEach((d) => { if (d.i < d.j && d.v != null && App.groupe(d.a, leg).famille !== App.groupe(d.c, leg).famille && (!best || d.v > best.v)) best = d; });
    if (best) card.append("p").attr("class", "note").text(`Rapprochement le plus fréquent entre familles différentes : ${best.a} et ${best.c}, d'accord sur ${F.pct(best.v)} des scrutins.`);
  },

  tableGroupes(card, g, leg) {
    card.html(`<h2>Discipline, présence, influence</h2><p class="sub">Par groupe. <b>Cohésion</b> : part des membres qui suivent la position du groupe. <b>Présence</b> : part des scrutins auxquels les membres prennent part. <b>Gagne</b> : part des votes où la position du groupe l'emporte.</p>`);
    const rows = g.ordre_groupes.map((s) => ({ s, ...g.groupes[s] }));
    card.append("table").attr("class", "bars").html(`
      <thead><tr><th>Groupe</th><th>Sièges</th><th>Cohésion</th><th>Présence</th><th>Gagne</th></tr></thead>
      <tbody>${rows.map((r) => `<tr class="click" data-s="${esc(r.s)}">
        <td>${chipGroupe(r.s, leg)}</td><td class="num">${sieges(r)}</td>
        <td>${cellBar(r.cohesion, r.couleur)}</td><td>${cellBar(r.participation, r.couleur, 0.5)}</td><td>${cellBar(r.reussite, r.couleur)}</td></tr>`).join("")}</tbody>`);
    card.selectAll("tr.click").on("click", function () { App.go("deputes", "groupe", this.dataset.s); });
    card.append("p").attr("class", "note").text("Les barres de présence vont jusqu'à 50 % : en séance, seuls les députés qui suivent un texte votent sur ses amendements.");
  },

  /* Sujets : volume et présence relative des familles */
  themes(card, g) {
    const th = Object.entries(g.themes).map(([code, v]) => ({ code, label: App.theme(code), ...v })).filter((t) => t.code !== "autre").sort((a, b) => b.n - a.n);
    // seulement les familles représentées par un groupe dans cette législature
    const fams = App.meta.familles.filter((f) => f.code !== "non_inscrits" && th.some((t) => t.participation[f.code] != null));
    card.html(`<h2>Qui s'intéresse à quoi</h2><p class="sub">À gauche, le nombre de scrutins par thème. À droite, selon le mode choisi : la présence relative de chaque famille (1,0 = sa présence habituelle ; au-dessus, elle se mobilise davantage), ou sa part de votes « pour ».</p>`);
    const tools = card.append("div").style("display", "flex").style("justify-content", "space-between").style("align-items", "center").style("margin-bottom", "8px");
    const seg = tools.append("div").attr("class", "seg");
    const legend = tools.append("div").attr("class", "legend").style("margin", 0);
    const wrap = card.append("div").attr("class", "chart");
    const modes = [["indice", "Présence relative"], ["pour_moyen", "Part de « pour »"]];
    let mode = "indice";
    seg.selectAll("button").data(modes).join("button").text((d) => d[1]).on("click", (e, d) => { mode = d[0]; draw(); });
    const draw = () => {
      seg.selectAll("button").classed("active", (d) => d[0] === mode);
      wrap.html("");
      const rowH = 24, L = 190, barW = 120, gap = 56, cw = 78, T = 40;
      const W = L + barW + gap + fams.length * cw, H = T + th.length * rowH + 4;
      const svg = wrap.append("svg").attr("viewBox", `0 0 ${W} ${H}`);
      const xb = d3.scaleLinear([0, d3.max(th, (t) => t.n)], [0, barW]);
      const col = mode === "indice"
        ? d3.scaleLinear([0.4, 1, 1.8], ["#b9772f", "#f4f5f7", "#1f4e99"]).clamp(true)
        : d3.scaleLinear([0, 0.6], ["#f2f5fa", "#1f4e99"]).clamp(true);
      legend.html(mode === "indice"
        ? `<span><span class="sw" style="background:#b9772f"></span>moins présente que d'habitude</span><span><span class="sw" style="background:#1f4e99"></span>plus présente</span>`
        : `<span><span class="sw" style="background:#f2f5fa;border:1px solid #e7e9ed"></span>peu de « pour »</span><span><span class="sw" style="background:#1f4e99"></span>beaucoup de « pour »</span>`);
      fams.forEach((f, j) => {
        const x0 = L + barW + gap + j * cw + cw / 2;
        svg.append("circle").attr("cx", x0).attr("cy", 10).attr("r", 4.5).attr("fill", f.couleur);
        const words = f.label.replace(" (LIOT)", "").split(" ");
        svg.append("text").attr("x", x0).attr("y", 26).attr("text-anchor", "middle").attr("font-size", 10.5).attr("fill", "#5b6370").text(words.join(" "));
      });
      const rows = svg.append("g").selectAll("g").data(th).join("g").attr("transform", (d, i) => `translate(0,${T + i * rowH})`);
      rows.append("text").attr("x", L - 10).attr("y", rowH / 2 + 4).attr("text-anchor", "end").attr("font-size", 12).attr("fill", "#1d2128").text((d) => d.label);
      rows.append("rect").attr("x", L).attr("y", 6).attr("height", rowH - 12).attr("rx", 3).attr("width", (d) => Math.max(2, xb(d.n))).attr("fill", "#9aa3ae");
      rows.append("text").attr("x", (d) => L + xb(d.n) + 5).attr("y", rowH / 2 + 4).attr("font-size", 10.5).attr("fill", "#5b6370").text((d) => F.int(d.n));
      fams.forEach((f, j) => {
        const x0 = L + barW + gap + j * cw;
        rows.append("rect").attr("x", x0 + 2).attr("y", 2).attr("width", cw - 4).attr("height", rowH - 4).attr("rx", 3)
          .attr("fill", (d) => (d[mode][f.code] == null ? "#fafafa" : col(d[mode][f.code])))
          .on("mouseenter", (e, d) => showTip(`<div class="tt-t">${esc(d.label)} · ${esc(f.label)}</div>${tipRows([
            ["Présence", d.participation[f.code] != null ? F.pct(d.participation[f.code]) : "—"],
            ["Présence relative", d.indice[f.code] != null ? F.dec(d.indice[f.code]) : "—"],
            ["Part de « pour »", d.pour_moyen[f.code] != null ? F.pct(d.pour_moyen[f.code]) : "—"],
          ])}`, e)).on("mousemove", moveTip).on("mouseleave", hideTip);
        rows.append("text").attr("x", x0 + cw / 2).attr("y", rowH / 2 + 4).attr("text-anchor", "middle").attr("font-size", 10.5).attr("pointer-events", "none")
          .attr("fill", (d) => {
            const v = d[mode][f.code];
            if (v == null) return "#8b929c";
            return mode === "indice" ? (v > 1.45 || v < 0.6 ? "#fff" : "#1d2128") : (v > 0.4 ? "#fff" : "#1d2128");
          })
          .text((d) => { const v = d[mode][f.code]; return v == null ? "" : mode === "indice" ? F.dec(v).replace(/0$/, "") : Math.round(v * 100) + " %"; });
      });
    };
    draw();
  },

  initiative(card, g, leg) {
    card.html(`<h2>Qui demande les scrutins, qui dépose les amendements</h2><p class="sub">Un scrutin public est demandé par un groupe ou le Gouvernement. Amendements : ceux qui ont été soumis à un scrutin public, et la part adoptée.</p>`);
    const rows = g.ordre_groupes.map((s) => ({ s, dem: g.demandeurs[s] || 0, aut: g.auteurs_amendements[s] || 0, ok: g.amendements_adoptes[s] || 0 }));
    const maxD = d3.max(rows, (r) => r.dem) || 1, maxA = d3.max(rows, (r) => r.aut) || 1;
    card.append("table").attr("class", "bars").html(`
      <thead><tr><th>Groupe</th><th>Scrutins demandés</th><th>Amendements votés</th><th>Adoptés</th></tr></thead>
      <tbody>${rows.map((r) => {
        const c = App.groupe(r.s, leg).couleur;
        return `<tr><td>${chipGroupe(r.s, leg)}</td>
        <td>${cellBar(r.dem, c, maxD, F.int)}</td><td>${cellBar(r.aut, c, maxA, F.int)}</td>
        <td class="num">${r.aut ? F.pct(r.ok / r.aut) : "—"}</td></tr>`;
      }).join("")}</tbody>`);
    if (g.demandeurs.Gouvernement) card.append("p").attr("class", "note").text(`Le Gouvernement a demandé ${F.int(g.demandeurs.Gouvernement)} scrutins publics.`);
  },

  dossiers(card, g) {
    card.html(`<h2>Les textes les plus disputés</h2><p class="sub">Dossiers ayant donné lieu au plus grand nombre de scrutins publics.</p>`);
    const max = g.top_dossiers[0]?.n || 1;
    card.append("table").attr("class", "bars").html(`<tbody>${g.top_dossiers.slice(0, 12).map((d) => `
      <tr><td style="max-width:300px">${esc(d.titre)}</td><td style="width:170px">${cellBar(d.n, "#3C6FB0", max, F.int)}</td></tr>`).join("")}</tbody>`);
  },
};
