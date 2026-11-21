/* Onglet « Scrutins » */
const Scrutins = {
  filtre: { q: "", theme: "", objet: "", resultat: "", serre: false, texte: false, tri: "date" },
  vue: { mode: "vote", on: new Set(["p", "c", "a", "n", " "]), focus: "p" },

  async render(main, route) {
    const b = await App.bundle();
    main.html("");
    let uid = route.a;
    if (!uid || !b.scrIndex.has(uid)) {
      const ens = [...b.scrutins].reverse().find((s) => s.o === "ensemble");
      uid = (ens || b.scrutins[b.scrutins.length - 1]).uid;
    }
    const layout = main.append("div").attr("class", "grid g-side");
    this.sidebar(layout.append("div").attr("class", "side"), b, uid);
    const panel = layout.append("div");
    panel.html('<div class="loading">Chargement du scrutin…</div>');
    const det = await App.detail(uid);
    panel.html("");
    this.fiche(panel, b, b.scrIndex.get(uid), det);
  },

  sidebar(side, b, uid) {
    const f = side.append("div").attr("class", "filters");
    const flt = this.filtre;
    f.append("input").attr("type", "search").attr("placeholder", "Rechercher (texte, amendement, auteur)…").property("value", flt.q)
      .on("input", (e) => { flt.q = e.target.value; fill(true); });
    const sel = (parent, key, opts) => {
      const s = parent.append("select").on("change", (e) => { flt[key] = e.target.value; fill(true); });
      opts.forEach(([v, l]) => s.append("option").attr("value", v).text(l));
      s.property("value", flt[key]);
    };
    const themesPresents = new Set(b.scrutins.map((s) => s.th));
    sel(f, "theme", [["", "Tous les thèmes"], ...App.meta.themes.filter((t) => themesPresents.has(t.code)).map((t) => [t.code, t.label])]);
    const row = f.append("div").attr("class", "row2");
    sel(row, "objet", [["", "Tous les objets"], ["amend", "Amendements"], ["article", "Articles"], ["ensemble", "Ensemble d'un texte"], ["motion", "Motions"]]);
    sel(row, "resultat", [["", "Adoptés et rejetés"], ["a", "Adoptés"], ["r", "Rejetés"]]);
    const row2 = f.append("div").attr("class", "row2");
    const chk = (parent, key, label) => {
      const l = parent.append("label").attr("class", "check");
      l.append("input").attr("type", "checkbox").property("checked", flt[key]).on("change", (e) => { flt[key] = e.target.checked; fill(true); });
      l.append("span").text(label);
    };
    chk(row2, "serre", "Votes serrés");
    chk(row2, "texte", "Avec texte");
    sel(f, "tri", [["date", "Les plus récents"], ["serre", "Les plus serrés"], ["votants", "Les plus suivis"]]);
    const count = f.append("div").attr("class", "count");
    const list = side.append("div").attr("class", "list");
    const more = side.append("div").attr("class", "more");
    const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    let lim = 120;
    const fill = (reset) => {
      if (reset) lim = 120;
      const q = norm(flt.q);
      const okObjet = (o) => !flt.objet || (flt.objet === "amend" ? o === "amendement" || o === "sous_amendement"
        : flt.objet === "motion" ? o.startsWith("motion") : flt.objet === "ensemble" ? o === "ensemble" || o === "partie_budget" : o === flt.objet);
      let rows = b.scrutins.filter((s) => (!flt.theme || s.th === flt.theme) && okObjet(s.o) && (!flt.resultat || s.r === flt.resultat)
        && (!flt.serre || (s.m < 0.1 && s.v[0] + s.v[1] >= 20)) && (!flt.texte || s.tx)
        && (!q || norm(s.i).includes(q) || norm(s.dt).includes(q) || norm(s.au).includes(q)));
      if (flt.tri === "serre") rows = rows.filter((s) => s.v[0] + s.v[1] >= 20).sort((a, c) => a.m - c.m);
      else if (flt.tri === "votants") rows.sort((a, c) => d3.sum(c.v) - d3.sum(a.v));
      else rows = rows.slice().reverse();
      count.text(`${F.int(rows.length)} scrutin${rows.length > 1 ? "s" : ""}`);
      list.selectAll(".item").data(rows.slice(0, lim), (s) => s.uid).join("div")
        .attr("class", (s) => "item" + (s.uid === uid ? " sel" : ""))
        .html((s) => {
          const tot = s.v[0] + s.v[1] + s.v[2] || 1;
          return `<div class="m"><span>${F.date(s.d)}</span><span>·</span><span>${OBJETS[s.o] || s.o}</span><span style="margin-left:auto">${badgeResultat(s.r)}</span></div>
            <div class="t">${esc(s.i.charAt(0).toUpperCase() + s.i.slice(1))}</div>
            <div class="mini"><div style="width:${(s.v[0] / tot) * 100}%;background:${VOTE.p.color}"></div><div style="width:${(s.v[2] / tot) * 100}%;background:${VOTE.a.color}"></div><div style="width:${(s.v[1] / tot) * 100}%;background:${VOTE.c.color}"></div></div>`;
        })
        .on("click", (e, s) => App.go("scrutins", s.uid));
      more.html(rows.length > lim ? `<button>Afficher plus</button>` : "");
      more.select("button").on("click", () => { lim += 200; fill(); });
    };
    fill(true);
    const s = list.select(".item.sel").node();
    if (s) s.scrollIntoView({ block: "center" });
  },

  fiche(panel, b, j, det) {
    const s = b.scrutins[j];
    const row = b.matrice[j];
    // membres en fonction ce jour-là + votants hors mandat éventuels
    const votants = [];
    for (let i = 0; i < row.length; i++) if (row[i] !== " ") votants.push(i);
    const items = Hemicycle.membres(b, s.d, votants).map((it) => ({ ...it, v: row[it.i] }));
    const counts = d3.rollup(items, (v) => v.length, (d) => d.v);
    const cnt = (k) => counts.get(k) || 0;

    const titre = det.intitule.charAt(0).toUpperCase() + det.intitule.slice(1);
    panel.append("div").attr("class", "detail-head").html(`<div>
      <div class="meta"><span>Scrutin n° ${det.numero}</span><span>·</span><span>${F.dateLong(det.date)}</span>
        <span class="badge b-type">${det.type_vote === "solennel" ? "Scrutin solennel" : det.type_vote === "motion_de_censure" ? "Motion de censure" : "Scrutin ordinaire"}</span>
        <span class="badge b-type">${OBJETS[det.objet_vote] || det.objet_vote}</span><span class="badge b-type">${esc(App.theme(s.th))}</span></div>
      <h1>${esc(titre)}</h1></div>`);

    // ---- résultat
    const top = panel.append("div").attr("class", "card");
    const exprimes = det.decompte.pour + det.decompte.contre;
    top.html(`<div style="display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;align-items:flex-start">
      <div class="tally">
        <div class="t-item"><div class="v">${badgeResultat(det.resultat)}</div><div class="l">${exprimes ? `écart de ${F.int(Math.abs(det.decompte.pour - det.decompte.contre))} voix` : ""}</div></div>
        ${[["p", det.decompte.pour], ["c", det.decompte.contre], ["a", det.decompte.abstentions], ["n", det.decompte.nonVotants], [" ", cnt(" ")]]
          .map(([k, v]) => `<div class="t-item"><div class="v">${F.int(v)}</div><div class="l"><span class="sw" style="background:${VOTE[k].color}"></span>${k === " " ? "Absents" : VOTE[k].label}</div></div>`).join("")}
      </div></div>
      <dl class="facts">
        ${det.dossier.titre ? `<dt>Texte</dt><dd>${det.url_dossier ? `<a href="${det.url_dossier}" target="_blank" rel="noopener">${esc(det.dossier.titre)}</a>` : esc(det.dossier.titre)}${det.dossier.lecture ? ` <span class="muted">(${esc(det.dossier.lecture)})</span>` : ""}</dd>` : ""}
        ${det.auteur && det.auteur.texte ? `<dt>Auteur</dt><dd>${det.auteur.depute_id && b.depIndex.has(det.auteur.depute_id) ? `<a href="#/${b.leg}/deputes/${det.auteur.depute_id}">${esc(det.auteur.texte)}</a>` : esc(det.auteur.texte)} ${det.auteur.groupe ? chipGroupe(det.auteur.groupe, b.leg) : ""}</dd>` : ""}
        ${det.demandeur ? `<dt>Scrutin demandé par</dt><dd>${esc(det.demandeur)}</dd>` : ""}
        <dt>Source</dt><dd><a href="${det.url_scrutin}" target="_blank" rel="noopener">Analyse du scrutin sur assemblee-nationale.fr</a></dd>
      </dl>`);

    // ---- hémicycle
    const hc = panel.append("div").attr("class", "card").style("margin-top", "16px");
    hc.html(`<h2>Qui a voté quoi</h2><p class="sub">Les ${F.int(items.length)} députés en fonction ce jour-là, vus depuis le perchoir (la gauche à gauche), regroupés par groupe politique. Survolez un siège pour le nom, cliquez pour la fiche.</p>`);
    const tools = hc.append("div").attr("class", "hemi-tools");
    const seg = tools.append("div").attr("class", "seg");
    const chips = tools.append("div").attr("class", "filters-chips");
    const legendFam = hc.append("div");
    const box = hc.append("div").attr("class", "chart").style("max-width", "860px").style("margin", "0 auto");
    const vue = this.vue;
    const famColor = (d) => App.famille(App.groupe(d.groupe, b.leg).famille).couleur;
    const allume = (d) => (vue.focus === "tous" ? "pca".includes(d.v) : d.v === vue.focus);
    const opts = {
      fill: (d) => vue.mode === "vote" ? VOTE[d.v].color : (allume(d) ? famColor(d) : "#fff"),
      stroke: (d) => vue.mode === "vote" ? (d.v === "n" ? "#5b6370" : "none") : (allume(d) ? "none" : famColor(d)),
      strokeWidth: (d) => vue.mode === "vote" ? (d.v === "n" ? 1 : 0) : (allume(d) ? 0 : 0.9),
      opacity: (d) => vue.mode === "vote" ? (vue.on.has(d.v) ? 1 : 0.12) : (allume(d) ? 1 : 0.45),
      tip: (d) => `<div class="tt-t">${esc(d.dep.nom)}</div>${tipRows([["Groupe", d.groupe], ["Vote", VOTE[d.v].label]])}`,
      click: (d) => App.go("deputes", d.dep.id),
      center: [det.resultat.startsWith("adopt") ? "Adopté" : "Rejeté", `${F.int(det.decompte.pour)} pour · ${F.int(det.decompte.contre)} contre`],
      label: `Hémicycle du scrutin ${det.numero}`,
    };
    const hemi = Hemicycle.draw(box, items, opts);
    let drawTools = () => {
      seg.selectAll("button").data([["vote", "Couleur du vote"], ["famille", "Couleur de la famille"]]).join("button")
        .text((d) => d[1]).classed("active", (d) => d[0] === vue.mode)
        .on("click", (e, d) => { vue.mode = d[0]; drawTools(); hemi.update(opts); });
      if (vue.mode === "vote") {
        legendFam.html("");
        chips.selectAll(".fchip").data(["p", "c", "a", "n", " "]).join("span").attr("class", (k) => "fchip" + (vue.on.has(k) ? "" : " off"))
          .attr("title", "Cliquer pour masquer / afficher")
          .html((k) => `<span class="sw" style="background:${VOTE[k].color};${k === "n" ? "border:1px solid #5b6370" : ""}"></span>${k === " " ? "Absents" : VOTE[k].label} <span class="n">${F.int(cnt(k))}</span>`)
          .on("click", (e, k) => {
            if (vue.on.has(k) && vue.on.size === 5) vue.on = new Set([k]);       // premier clic : isoler
            else if (vue.on.has(k)) vue.on.delete(k); else vue.on.add(k);
            if (!vue.on.size) vue.on = new Set(["p", "c", "a", "n", " "]);
            drawTools(); hemi.update(opts);
          });
      } else {
        const fams = App.meta.familles.filter((f) => items.some((d) => App.groupe(d.groupe, b.leg).famille === f.code));
        legendFam.html(`<div class="legend" style="justify-content:center">${fams.map((f) => `<span><span class="sw dot" style="background:${f.couleur}"></span>${esc(f.label)}</span>`).join("")}
          <span><span class="sw dot" style="background:#fff;border:1px solid #8b929c"></span>siège éteint</span></div>`);
        chips.selectAll(".fchip").data(["p", "c", "a", "tous"]).join("span").attr("class", (k) => "fchip" + (vue.focus === k ? "" : " off"))
          .attr("title", "Allumer les sièges qui ont voté ainsi")
          .html((k) => k === "tous" ? `Tous les votants <span class="n">${F.int(cnt("p") + cnt("c") + cnt("a"))}</span>`
            : `<span class="sw" style="background:${VOTE[k].color}"></span>${VOTE[k].label} <span class="n">${F.int(cnt(k))}</span>`)
          .on("click", (e, k) => { vue.focus = k; drawTools(); hemi.update(opts); });
      }
    };
    const noteHemi = hc.append("div").attr("class", "note").style("text-align", "center");
    const _draw = drawTools;
    drawTools = () => {
      _draw();
      noteHemi.text(vue.mode === "famille"
        ? "Choisissez un vote : les sièges qui l'ont émis s'allument dans la couleur de leur famille politique, les autres restent éteints."
        : "Cliquez sur un vote pour l'isoler, puis sur les autres pour les rajouter.");
    };
    drawTools();

    // ---- par groupe
    const gc = panel.append("div").attr("class", "card").style("margin-top", "16px");
    gc.html(`<h2>Le vote de chaque groupe</h2><p class="sub">Tous les membres du groupe ce jour-là, absents compris.</p>`);
    gc.append("div").html(legendHTML(["p", "a", "c", "n", " "].map((k) => ({ label: k === " " ? "Absents" : VOTE[k].label, color: VOTE[k].color })), true));
    const parG = d3.groups(items, (d) => d.groupe).sort((x, y) => App.groupe(x[0], b.leg).rang - App.groupe(y[0], b.leg).rang);
    const maxN = d3.max(parG, ([, v]) => v.length);
    gc.append("table").attr("class", "bars").html(`<thead><tr><th>Groupe</th><th></th><th>Pour</th><th>Contre</th><th>Abst.</th><th>Position</th></tr></thead><tbody>${parG.map(([g, v]) => {
      const c = (k) => v.filter((d) => d.v === k).length;
      const pos = det.positions_groupes[g]?.position;
      const posTxt = det.objet_vote === "motion_censure" ? (pos === "pour" ? badgeVote("p") : '<span class="muted small">ne soutient pas</span>')
        : pos ? badgeVote({ pour: "p", contre: "c", abstention: "a" }[pos]) : '<span class="muted">—</span>';
      return `<tr class="click" data-s="${esc(g)}"><td style="width:100px">${chipGroupe(g, b.leg)}</td>
        <td style="width:42%"><div class="split" style="width:${(v.length / maxN) * 100}%">${["p", "a", "c", "n", " "].map((k) => (c(k) ? `<div style="flex:${c(k)};background:${VOTE[k].color}" title="${VOTE[k].label} : ${c(k)}"></div>` : "")).join("")}</div></td>
        <td class="num">${c("p") || ""}</td><td class="num">${c("c") || ""}</td><td class="num">${c("a") || ""}</td><td>${posTxt}</td></tr>`;
    }).join("")}</tbody>`);
    gc.selectAll("tr.click").on("click", function () { App.go("deputes", "groupe", this.dataset.s); });

    // ---- textes
    const t = det.texte || {};
    const tl = det.texte_loi;
    if (t.dispositif || t.expose_sommaire || tl) {
      const tc = panel.append("div").attr("class", "card").style("margin-top", "16px");
      tc.html(`<h2>Le texte voté</h2>`);
      if (t.dispositif || t.expose_sommaire) {
        tc.append("p").attr("class", "sub").html(`Amendement n° ${esc(t.numero_amendement)}${t.article ? ` · ${esc(t.article)}` : ""}${t.qualite_jointure === "probable" ? " · <i>rapprochement probable</i>" : ""}`);
        if (t.dispositif) tc.append("div").attr("class", "prose").style("background", "#f7f8fa").style("padding", "12px 14px").style("border-radius", "8px").text(t.dispositif);
        if (t.expose_sommaire) {
          const d = tc.append("details").attr("class", "block").property("open", true);
          d.append("summary").text("Exposé sommaire (argumentaire de l'auteur)");
          d.append("div").attr("class", "prose").text(t.expose_sommaire);
        }
        if (t.signataires) {
          const d = tc.append("details").attr("class", "block");
          d.append("summary").text("Signataires");
          d.append("div").attr("class", "small muted").text(t.signataires);
        }
      }
      if (tl) {
        if (tl.expose) {
          const d = tc.append("details").attr("class", "block").property("open", !(t.dispositif || t.expose_sommaire));
          d.append("summary").text(`Exposé des motifs du texte${tl.titre ? " — " + tl.titre.slice(0, 90) + (tl.titre.length > 90 ? "…" : "") : ""}`);
          const dv = d.append("div");
          dv.append("div").attr("class", "prose").text(tl.expose + (tl.expose_tronque ? "\n[…]" : ""));
          dv.append("p").attr("class", "small").html(`<a href="${tl.url}" target="_blank" rel="noopener">Texte complet sur assemblee-nationale.fr</a>`);
        } else {
          const d = tc.append("details").attr("class", "block");
          d.append("summary").text("Texte de la loi");
          d.append("div").attr("class", "small muted").html(`${tl.note === "transmis_par_le_senat_sans_expose" ? "Texte transmis par le Sénat : son exposé des motifs se trouve dans la version déposée au Sénat."
            : tl.note === "loi_de_finances_format_specifique" ? "Loi de finances : exposé des motifs trop volumineux pour être affiché ici." : "Pas d'exposé des motifs disponible."}
            <a href="${tl.url}" target="_blank" rel="noopener">Voir le texte</a>`);
        }
        if (tl.articles) {
          const d = tc.append("details").attr("class", "block");
          d.append("summary").text("Articles du texte déposé");
          d.append("div").attr("class", "prose").text(tl.articles + (tl.articles_tronques ? "\n[…]" : ""));
        }
      }
    }

    if (det.mises_au_point && det.mises_au_point.length) {
      const mc = panel.append("div").attr("class", "card").style("margin-top", "16px");
      mc.html(`<h2>Mises au point</h2><p class="sub">Députés ayant déclaré après coup qu'ils voulaient voter autrement. Le vote officiel reste celui de l'hémicycle.</p>`);
      const lab = { pour: "p", contre: "c", abstention: "a", non_votant: "n", non_votant_volontaire: "n" };
      mc.append("table").attr("class", "bars").html(`<thead><tr><th>Député</th><th>Vote enregistré</th><th>Vote voulu</th></tr></thead><tbody>${det.mises_au_point.map((m) =>
        `<tr><td>${b.depIndex.has(m.id) ? `<a href="#/${b.leg}/deputes/${m.id}">${esc(m.nom)}</a>` : esc(m.nom)}</td><td>${badgeVote(lab[m.vote])}</td><td>${badgeVote(lab[m.voulu])}</td></tr>`).join("")}</tbody>`);
    }
  },
};
