/* Onglet « Députés & groupes » */
const Deputes = {
  filtre: { q: "", groupe: "", tri: "nom" },

  async render(main, route) {
    const b = await App.bundle();
    main.html("");
    const layout = main.append("div").attr("class", "grid g-side");
    this.sidebar(layout.append("div").attr("class", "side"), b, route);
    const panel = layout.append("div");
    if (route.a === "groupe" && route.b) this.groupe(panel, b, route.b);
    else if (route.a && b.depIndex.has(route.a)) this.depute(panel, b, b.depIndex.get(route.a));
    else this.accueil(panel, b);
  },

  sidebar(side, b, route) {
    const f = side.append("div").attr("class", "filters");
    f.append("input").attr("type", "search").attr("placeholder", "Rechercher un député…").property("value", this.filtre.q)
      .on("input", (e) => { this.filtre.q = e.target.value; fill(); });
    const row = f.append("div").attr("class", "row2");
    const sg = row.append("select").on("change", (e) => { this.filtre.groupe = e.target.value; fill(); });
    sg.append("option").attr("value", "").text("Tous les groupes");
    b.general.ordre_groupes.forEach((s) => sg.append("option").attr("value", s).text(s));
    sg.property("value", this.filtre.groupe);
    const st = row.append("select").on("change", (e) => { this.filtre.tri = e.target.value; fill(); });
    [["nom", "Tri : nom"], ["participation", "Tri : présence"], ["loyaute", "Tri : frondeurs"], ["x", "Tri : gauche → droite"]]
      .forEach(([v, l]) => st.append("option").attr("value", v).text(l));
    st.property("value", this.filtre.tri);
    const count = f.append("div").attr("class", "count");
    const list = side.append("div").attr("class", "list");
    const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    const fill = () => {
      const q = norm(this.filtre.q);
      let rows = b.deputes.filter((d) => (!q || norm(d.nom).includes(q) || norm(d.dept).includes(q)) && (!this.filtre.groupe || d.groupes.some((g) => g[0] === this.filtre.groupe) || d.groupe === this.filtre.groupe));
      const t = this.filtre.tri;
      if (t === "participation") rows.sort((a, c) => (c.participation ?? -1) - (a.participation ?? -1));
      else if (t === "loyaute") rows.sort((a, c) => (a.loyaute ?? 2) - (c.loyaute ?? 2));
      else if (t === "x") rows.sort((a, c) => (a.x ?? 0) - (c.x ?? 0));
      else rows.sort((a, c) => (a.nom || "").localeCompare(c.nom || "", "fr"));
      count.text(`${rows.length} député${rows.length > 1 ? "s" : ""}`);
      list.selectAll(".item").data(rows, (d) => d.id).join("div")
        .attr("class", (d) => "item" + (d.id === route.a ? " sel" : ""))
        .html((d) => {
          const c = App.groupe(d.groupe, b.leg).couleur;
          const extra = t === "participation" ? `présence ${d.participation != null ? F.pct(d.participation) : "—"}`
            : t === "loyaute" ? `vote avec son groupe ${d.loyaute != null ? F.pct(d.loyaute) : "—"}`
            : `${esc(d.dept || "")}`;
          return `<div class="dep"><span class="sw" style="background:${c}"></span><div><div class="t">${esc(d.nom)}</div>
            <div class="m">${esc(d.groupe)} · ${extra}</div></div></div>`;
        })
        .on("click", (e, d) => App.go("deputes", d.id));
    };
    fill();
    const sel = list.select(".item.sel").node();
    if (sel) sel.scrollIntoView({ block: "center" });
  },

  accueil(panel, b) {
    const g = b.general;
    panel.append("div").attr("class", "page-head").html(`<div><h1>Les groupes politiques</h1>
      <p>Choisissez un groupe pour voir ses membres, sa discipline et ses alliances, ou un député dans la liste pour voir comment il vote.</p></div>`);
    const cards = panel.append("div").attr("class", "group-cards");
    g.ordre_groupes.forEach((s) => {
      const gr = g.groupes[s];
      cards.append("div").attr("class", "gcard").style("--c", gr.couleur).html(`
        <div class="s">${esc(s)}</div><div class="n">${esc(gr.nom || "")}</div>
        <div class="stats">
          <div><div class="v">${sieges(gr)}</div><div class="l">${gr.effectif_dernier ? "sièges" : `jusqu'à ${gr.effectif_max} sièges`}</div></div>
          <div><div class="v">${gr.cohesion != null ? F.pct(gr.cohesion) : "—"}</div><div class="l">cohésion</div></div>
          <div><div class="v">${gr.reussite != null ? F.pct(gr.reussite) : "—"}</div><div class="l">gagne</div></div>
        </div>`).on("click", () => App.go("deputes", "groupe", s));
    });
    const hc = panel.append("div").attr("class", "card").style("margin-top", "16px");
    hc.html(`<h2>${b.leg === 17 ? "L'hémicycle aujourd'hui" : "L'hémicycle en fin de législature"}</h2><p class="sub">Sièges au ${F.dateLong(g.periode[1])}, vus depuis le perchoir : la gauche à gauche. Survolez un siège, cliquez pour ouvrir la fiche.</p>`);
    const items = Hemicycle.membres(b, g.periode[1]);
    hc.append("div").html(legendHTML(g.ordre_groupes.map((s) => ({ label: s, color: App.groupe(s, b.leg).couleur })), true));
    Hemicycle.draw(hc.append("div").attr("class", "chart").style("max-width", "820px").style("margin", "0 auto"), items, {
      fill: (d) => App.groupe(d.groupe, b.leg).couleur,
      tip: (d) => `<div class="tt-t">${esc(d.dep.nom)}</div>${tipRows([["Groupe", d.groupe], ["Circonscription", d.dep.dept ? `${esc(d.dep.dept)} (${d.dep.circo})` : "—"]])}`,
      click: (d) => App.go("deputes", d.dep.id),
      center: [F.int(items.length), "députés en fonction"],
    });
  },

  /* ---------------- fiche groupe ---------------- */
  groupe(panel, b, sig) {
    const g = b.general, gr = g.groupes[sig];
    if (!gr) { panel.html(`<div class="empty">Groupe inconnu pour cette législature.</div>`); return; }
    const fam = App.famille(gr.famille);
    panel.append("div").attr("class", "detail-head").html(`<div>
      <div class="meta"><a href="#/${b.leg}/deputes">← Tous les groupes</a><span class="chip"><span class="sw" style="background:${fam.couleur}"></span>${esc(fam.label)}</span></div>
      <h1><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${gr.couleur};margin-right:8px"></span>${esc(sig)} — ${esc(gr.nom || "")}</h1></div>`);
    panel.append("div").attr("class", "kpis").html([
      [gr.effectif_dernier || "—", gr.effectif_dernier ? "sièges" : "groupe dissous", `jusqu'à ${gr.effectif_max} au cours de la législature`],
      [gr.cohesion != null ? F.pct(gr.cohesion) : "—", "cohésion", "membres qui suivent la ligne du groupe"],
      [F.pct(gr.participation), "présence", "scrutins auxquels les membres votent"],
      [gr.reussite != null ? F.pct(gr.reussite) : "—", "gagne", `la position du groupe l'emporte (${F.int(gr.n_positions)} votes)`],
      [F.int(g.demandeurs[sig] || 0), "scrutins demandés", `${F.int(g.auteurs_amendements[sig] || 0)} amendements soumis au vote`],
    ].map(([v, l, h]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="h">${h}</div></div>`).join(""));

    const r = panel.append("div").attr("class", "grid g2");
    const hc = r.append("div").attr("class", "card");
    // dernière date où le groupe existait (utile pour les groupes dissous en cours de législature)
    const fins = b.deputes.flatMap((d) => d.groupes.filter((x) => x[0] === sig).map((x) => x[2] || g.periode[1]));
    const dateG = fins.length ? d3.min([d3.max(fins), g.periode[1]]) : g.periode[1];
    hc.html(`<h2>Ses sièges</h2><p class="sub">Au ${F.dateLong(dateG)}.</p>`);
    const items = Hemicycle.membres(b, dateG);
    Hemicycle.draw(hc.append("div").attr("class", "chart"), items, {
      fill: (d) => (d.groupe === sig ? gr.couleur : "#e9ebee"),
      tip: (d) => `<div class="tt-t">${esc(d.dep.nom)}</div>${tipRows([["Groupe", d.groupe]])}`,
      click: (d) => App.go("deputes", d.dep.id),
    });
    const acc = r.append("div").attr("class", "card");
    acc.html(`<h2>Ses alliances</h2><p class="sub">Part des scrutins où ${esc(sig)} a pris la même position que chaque autre groupe.</p>`);
    const rows = g.ordre_groupes.filter((s) => s !== sig && g.accords_groupes[sig]?.[s] != null)
      .map((s) => ({ s, v: g.accords_groupes[sig][s] })).sort((a, c) => c.v - a.v);
    acc.append("table").attr("class", "bars").html(`<tbody>${rows.map((x) => `<tr class="click" data-s="${esc(x.s)}"><td style="width:110px">${chipGroupe(x.s, b.leg)}</td><td>${cellBar(x.v, App.groupe(x.s, b.leg).couleur)}</td></tr>`).join("")}</tbody>`);
    acc.selectAll("tr.click").on("click", function () { App.go("deputes", "groupe", this.dataset.s); });

    const membres = b.deputes.filter((d) => d.groupes.some((x) => x[0] === sig) || d.groupe === sig);
    const mc = panel.append("div").attr("class", "card").style("margin-top", "16px");
    mc.html(`<h2>Ses membres</h2><p class="sub">${membres.length} députés ont appartenu au groupe. Triés par fidélité au groupe : les plus frondeurs en premier.</p>`);
    membres.sort((a, c) => (a.loyaute ?? 2) - (c.loyaute ?? 2));
    mc.append("table").attr("class", "bars").html(`<thead><tr><th>Député</th><th>Circonscription</th><th>Présence</th><th>Vote avec son groupe</th></tr></thead>
      <tbody>${membres.map((d) => `<tr class="click" data-id="${d.id}"><td>${esc(d.nom)}${d.groupe !== sig ? ` <span class="muted small">(aujourd'hui ${esc(d.groupe)})</span>` : ""}</td>
        <td class="muted">${esc(d.dept || "—")}</td><td style="width:180px">${cellBar(d.participation, gr.couleur, 0.6)}</td><td style="width:200px">${cellBar(d.loyaute, gr.couleur)}</td></tr>`).join("")}</tbody>`);
    mc.selectAll("tr.click").on("click", function () { App.go("deputes", this.dataset.id); });
  },

  /* ---------------- fiche député ---------------- */
  depute(panel, b, i) {
    const d = b.deputes[i];
    const gr = App.groupe(d.groupe, b.leg);
    const fam = App.famille(d.famille);
    const fin = d.mandats && d.mandats.length ? d.mandats[d.mandats.length - 1][1] : null;
    const histo = d.groupes.length > 1
      ? d.groupes.map(([s, deb, f]) => `${chipGroupe(s, b.leg)} <span class="muted small">${F.date(deb)} → ${f ? F.date(f) : "aujourd'hui"}</span>`).join(" ")
      : chipGroupe(d.groupe, b.leg);
    panel.append("div").attr("class", "detail-head").html(`<div>
      <div class="meta">${histo}<span class="chip"><span class="sw" style="background:${fam.couleur}"></span>${esc(fam.label)}</span></div>
      <h1>${esc(d.nom)}</h1>
      <div class="muted" style="margin-top:4px">${d.dept ? `${d.civ === "Mme" ? "Députée" : "Député"} de ${esc(d.dept)} (${esc(d.num_dept)}), ${esc(d.circo)}<sup>e</sup> circonscription` : ""}
      ${d.mandats ? ` · en fonction ${d.mandats.map(([a, z]) => `du ${F.date(a)}${z ? ` au ${F.date(z)}` : ""}`).join(", ")}` : ""}</div></div>`);

    // ses votes
    const votes = [];
    for (let j = 0; j < b.scrutins.length; j++) {
      const c = b.matrice[j][i];
      if (c === " ") continue;
      const s = b.scrutins[j];
      const gs = groupeALaDate(d, s.d);
      const pg = s.o === "motion_censure" ? null : s.pos[gs];
      votes.push({ s, c, gs, pg, frondeur: "pca".includes(c) && "pca".includes(pg || "-") && c !== pg });
    }
    const n = d.n, nexp = n.p + n.c + n.a;
    const nf = votes.filter((v) => v.frondeur).length;
    panel.append("div").attr("class", "kpis").html([
      [F.int(votes.length), "votes", `${F.int(nexp)} exprimés, ${F.int(n.nv)} non-votant`],
      [d.participation != null ? F.pct(d.participation) : "—", "présence", `moyenne de l'Assemblée : ${F.pct(b.general.participation_moyenne)}`],
      [d.loyaute != null ? F.pct(d.loyaute) : "—", "vote avec son groupe", `${F.int(nf)} votes contre la ligne du groupe`],
      [nexp ? F.pct(n.p / nexp) : "—", "de « pour »", "parmi ses votes exprimés"],
      [d.x != null ? (d.x < -0.33 ? "gauche" : d.x > 0.33 ? "droite" : "centre") : "—", "position sur la carte", d.x != null ? `axe 1 : ${F.dec(d.x)}` : "trop peu de votes"],
    ].map(([v, l, h]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="h">${h}</div></div>`).join(""));

    const r = panel.append("div").attr("class", "grid g2");
    const hc = r.append("div").attr("class", "card");
    const date = fin && fin < b.general.periode[1] ? fin : b.general.periode[1];
    hc.html(`<h2>Où ${d.civ === "Mme" ? "elle" : "il"} siège</h2><p class="sub">Place dans l'hémicycle reconstitué au ${F.dateLong(date)} : groupes de gauche à droite, et à l'intérieur de chaque groupe, ordre de la carte politique.</p>`);
    const items = Hemicycle.membres(b, date, [i]);
    Hemicycle.draw(hc.append("div").attr("class", "chart"), items, {
      fill: (x) => (x.i === i ? App.groupe(x.groupe, b.leg).couleur : "#e9ebee"),
      radius: (x, r0) => (x.i === i ? r0 * 1.9 : r0),
      stroke: (x) => (x.i === i ? "#1d2128" : "none"),
      strokeWidth: (x) => (x.i === i ? 2 : 0),
      tip: (x) => `<div class="tt-t">${esc(x.dep.nom)}</div>${tipRows([["Groupe", x.groupe]])}`,
      click: (x) => App.go("deputes", x.dep.id),
    });
    hc.selectAll("circle.seat").filter((x) => x.i === i).raise();

    const ac = r.append("div").attr("class", "card");
    ac.html(`<h2>Avec quels groupes ${d.civ === "Mme" ? "elle" : "il"} vote</h2><p class="sub">Part de ses votes identiques à la position majoritaire de chaque groupe.</p>`);
    const rows = b.general.ordre_groupes.filter((s) => d.acc_groupes[s] != null).map((s) => ({ s, v: d.acc_groupes[s] }));
    ac.append("table").attr("class", "bars").html(`<tbody>${rows.map((x) => `<tr class="click" data-s="${esc(x.s)}"><td style="width:110px">${chipGroupe(x.s, b.leg)}</td><td>${cellBar(x.v, App.groupe(x.s, b.leg).couleur)}</td></tr>`).join("")}</tbody>`);
    ac.selectAll("tr.click").on("click", function () { App.go("deputes", "groupe", this.dataset.s); });

    const r2 = panel.append("div").attr("class", "grid g2").style("margin-top", "16px");
    // votes par thème
    const tc = r2.append("div").attr("class", "card");
    tc.html(`<h2>Ses sujets</h2><p class="sub">Nombre de votes par thème et répartition pour / contre / abstention.</p>`);
    tc.append("div").html(legendHTML(["p", "c", "a"].map((k) => ({ label: VOTE[k].label, color: VOTE[k].color })), true));
    const parTheme = d3.rollups(votes, (v) => ({ n: v.length, p: v.filter((x) => x.c === "p").length, c: v.filter((x) => x.c === "c").length, a: v.filter((x) => x.c === "a").length }), (v) => v.s.th)
      .filter(([k]) => k !== "autre").sort((a, c) => c[1].n - a[1].n).slice(0, 10);
    const maxT = d3.max(parTheme, ([, v]) => v.n) || 1;
    tc.append("table").attr("class", "bars").html(`<tbody>${parTheme.map(([k, v]) => {
      return `<tr><td style="width:190px">${esc(App.theme(k))}</td><td style="width:60%"><div class="split" style="width:${Math.max(4, (v.n / maxT) * 100)}%">
        ${["p", "c", "a"].map((key) => (v[key] ? `<div style="flex:${v[key]};background:${VOTE[key].color}"></div>` : "")).join("")}${v.n - v.p - v.c - v.a > 0 ? `<div style="flex:${v.n - v.p - v.c - v.a};background:${VOTE.n.color}"></div>` : ""}</div></td>
        <td class="num" style="width:44px;text-align:right">${F.int(v.n)}</td></tr>`;
    }).join("")}</tbody>`);

    const pc = r2.append("div").attr("class", "card");
    pc.html(`<h2>Les députés qui votent le plus comme ${d.civ === "Mme" ? "elle" : "lui"}</h2><p class="sub">Part de votes identiques, sur au moins 30 scrutins en commun.</p>`);
    pc.append("table").attr("class", "bars").html(`<tbody>${d.proches.map(([k, v]) => {
      const o = b.deputes[k];
      return `<tr class="click" data-id="${o.id}"><td>${esc(o.nom)}</td><td style="width:100px">${chipGroupe(o.groupe, b.leg)}</td><td style="width:170px">${cellBar(v, App.groupe(o.groupe, b.leg).couleur)}</td></tr>`;
    }).join("")}</tbody>`);
    pc.selectAll("tr.click").on("click", function () { App.go("deputes", this.dataset.id); });

    // liste des votes
    const vc = panel.append("div").attr("class", "card").style("margin-top", "16px");
    vc.html(`<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><div><h2>Ses votes</h2>
      <p class="sub" style="margin:2px 0 0">Du plus récent au plus ancien. Cliquez pour ouvrir le scrutin.</p></div></div>`);
    const seg = vc.select("div").append("div").attr("class", "seg");
    let mode = "tous", lim = 40;
    const modes = [["tous", `Tous (${F.int(votes.length)})`], ["frondeur", `Contre son groupe (${F.int(nf)})`], ["ens", "Votes sur l'ensemble d'un texte"]];
    seg.selectAll("button").data(modes).join("button").text((x) => x[1]).on("click", (e, x) => { mode = x[0]; lim = 40; draw(); });
    const tb = vc.append("table").attr("class", "bars").style("margin-top", "12px");
    const more = vc.append("div").attr("class", "more");
    const draw = () => {
      seg.selectAll("button").classed("active", (x) => x[0] === mode);
      const rowsV = votes.filter((v) => (mode === "frondeur" ? v.frondeur : mode === "ens" ? ["ensemble", "partie_budget", "motion_censure"].includes(v.s.o) : true)).reverse();
      tb.html(`<thead><tr><th>Date</th><th>Scrutin</th><th>Son vote</th><th>Son groupe</th><th>Résultat</th></tr></thead>
        <tbody>${rowsV.slice(0, lim).map((v) => `<tr class="click" data-uid="${v.s.uid}">
          <td class="muted num" style="white-space:nowrap">${F.date(v.s.d)}</td>
          <td><div style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(v.s.i)}</div></td>
          <td>${badgeVote(v.c)}</td>
          <td>${v.pg && "pca".includes(v.pg) ? badgeVote(v.pg) : '<span class="muted">—</span>'}</td>
          <td>${badgeResultat(v.s.r)}</td></tr>`).join("")}</tbody>`);
      tb.selectAll("tr.click").on("click", function () { App.go("scrutins", this.dataset.uid); });
      more.html(rowsV.length > lim ? `<button>Afficher plus (${F.int(rowsV.length - lim)} restants)</button>` : "");
      more.select("button").on("click", () => { lim += 80; draw(); });
    };
    draw();
  },
};
