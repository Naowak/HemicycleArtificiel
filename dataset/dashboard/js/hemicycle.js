/* Hémicycle : placement des sièges en arcs concentriques, gauche -> droite vu depuis le perchoir. */
const Hemicycle = {
  /* n sièges -> [{x, y, r}] dans un repère où le rayon extérieur vaut 1, triés de gauche à droite. */
  layout(n) {
    const rows = n > 450 ? 12 : n > 250 ? 10 : n > 120 ? 8 : n > 40 ? 5 : 3;
    const r0 = 0.36;
    const radii = d3.range(rows).map((i) => r0 + (1 - r0) * (i / (rows - 1)));
    const sum = d3.sum(radii);
    let counts = radii.map((r) => Math.round((n * r) / sum));
    let diff = n - d3.sum(counts);
    for (let i = rows - 1; diff !== 0; i = (i - 1 + rows) % rows) {
      counts[i] += Math.sign(diff);
      diff -= Math.sign(diff);
    }
    const seats = [];
    radii.forEach((r, i) => {
      const k = counts[i];
      for (let j = 0; j < k; j++) {
        const a = k === 1 ? Math.PI / 2 : Math.PI * (1 - j / (k - 1));
        seats.push({ a, r, row: i, x: r * Math.cos(a), y: r * Math.sin(a) });
      }
    });
    // ordre de remplissage : par angle décroissant (gauche d'abord), à angle égal du centre vers l'extérieur
    seats.sort((s, t) => t.a - s.a || s.r - t.r);
    const spacing = d3.min(radii.map((r, i) => (Math.PI * r) / Math.max(counts[i] - 1, 1)));
    const rowGap = (1 - r0) / (rows - 1);
    return { seats, dot: Math.min(spacing, rowGap) * 0.42 };
  },

  /* Membres en mandat à une date, ordonnés gauche -> droite (rang du groupe, puis axe 1 de l'ACP). */
  membres(bundle, date, extraIdx = []) {
    const out = [];
    const vus = new Set();
    bundle.deputes.forEach((d, i) => {
      const m = enMandat(d, date);
      if (m) { out.push(i); vus.add(i); }
    });
    for (const i of extraIdx) if (!vus.has(i)) out.push(i);
    const g = (i) => groupeALaDate(bundle.deputes[i], date);
    out.sort((i, j) => {
      const gi = App.groupe(g(i), bundle.leg), gj = App.groupe(g(j), bundle.leg);
      return gi.rang - gj.rang || (bundle.deputes[i].x ?? 0) - (bundle.deputes[j].x ?? 0);
    });
    return out.map((i) => ({ i, dep: bundle.deputes[i], groupe: g(i) }));
  },

  /* Dessine. items : [{i, dep, groupe, ...}] dans l'ordre gauche -> droite.
     opts.fill(item), opts.stroke(item), opts.opacity(item), opts.tip(item), opts.click(item), opts.radius(item) */
  draw(container, items, opts = {}) {
    const W = opts.width || 760, H = W * 0.53, R = W * 0.47;
    const { seats, dot } = this.layout(items.length);
    const cx = W / 2, cy = H - 14;
    const svg = container.append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
      .attr("aria-label", opts.label || "Hémicycle");
    const placed = items.map((it, k) => ({ ...it, sx: cx + seats[k].x * R, sy: cy - seats[k].y * R }));
    const rad = dot * R;
    const g = svg.append("g");
    const circles = g.selectAll("circle").data(placed).join("circle")
      .attr("class", "seat")
      .attr("cx", (d) => d.sx).attr("cy", (d) => d.sy)
      .attr("r", (d) => (opts.radius ? opts.radius(d, rad) : rad))
      .attr("fill", (d) => (opts.fill ? opts.fill(d) : "#ccc"))
      .attr("stroke", (d) => (opts.stroke ? opts.stroke(d) : "none"))
      .attr("stroke-width", (d) => (opts.strokeWidth ? opts.strokeWidth(d) : 1.2))
      .attr("opacity", (d) => (opts.opacity ? opts.opacity(d) : 1));
    if (opts.tip) {
      circles.on("mouseenter", (e, d) => { showTip(opts.tip(d), e); d3.select(e.currentTarget).attr("stroke", "#1d2128").attr("stroke-width", 1.6); })
        .on("mousemove", moveTip)
        .on("mouseleave", (e, d) => {
          hideTip();
          d3.select(e.currentTarget).attr("stroke", opts.stroke ? opts.stroke(d) : "none").attr("stroke-width", opts.strokeWidth ? opts.strokeWidth(d) : 1.2);
        });
    }
    if (opts.click) circles.on("click", (e, d) => { hideTip(); opts.click(d); });
    if (opts.center) {
      svg.append("text").attr("x", cx).attr("y", cy - R * 0.13).attr("text-anchor", "middle")
        .attr("font-size", 30).attr("font-weight", 650).attr("fill", "#1d2128").text(opts.center[0]);
      svg.append("text").attr("x", cx).attr("y", cy - R * 0.13 + 20).attr("text-anchor", "middle")
        .attr("font-size", 12).attr("fill", "#5b6370").text(opts.center[1]);
    }
    return { svg, circles, placed, update: (o) => {
      Object.assign(opts, o);
      circles.attr("fill", (d) => opts.fill(d)).attr("stroke", (d) => (opts.stroke ? opts.stroke(d) : "none"))
        .attr("stroke-width", (d) => (opts.strokeWidth ? opts.strokeWidth(d) : 1.2))
        .attr("opacity", (d) => (opts.opacity ? opts.opacity(d) : 1))
        .attr("r", (d) => (opts.radius ? opts.radius(d, rad) : rad));
    } };
  },
};
