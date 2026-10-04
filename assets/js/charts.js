// Charts built from the <table> inside each <figure class="chart">. The table stays in the HTML
// (hidden once the chart is drawn), so the numbers are in the page. Colours follow the paper's
// figures: compared methods in periwinkle, light to dark, and RadWorld in pink. The charts carry no
// value labels: values appear in a tooltip on hover, keyboard focus or tap, one method per line.
//
// Bar chart       <figure class="chart" data-scale="1">, one <tr> per horizontal bar
//   <tr data-tone="1|2|3"> compared method   <tr data-ours> RadWorld   <tr data-group="..."> group label
//   data-ref="50" on the figure draws a dashed reference line (for example chance level)
//
// Grouped columns <figure class="chart columns" data-min="0" data-max="300" data-ticks="0,100,200,300">
//   several methods on several benchmarks, as in the paper's bar charts. Header cells after the first
//   name the series (data-tone or data-ours), one <tr> per benchmark. data-panel on a row's first
//   cell starts a new panel (for example "CT" then "MRI"), and data-min, data-max and data-ticks on
//   that cell give the panel its own scale (one panel per metric). data-bar="14" allows thinner bars
//   before the chart switches to the narrow layout.
//
// Charts inside an element with data-same-bars share one bar width, set by the chart with the
// narrowest groups, so a chart with fewer groups gets more space between them instead of wider bars.
//
// Lollipop        <figure class="chart lollipop" data-min="0.3" data-max="1" data-ticks="...">
//   one comparison (two series) across many categories, as in the paper's Figure 2b.
//
// Grouped columns and lollipops also get a horizontal layout for narrow cards (phones): one label
// line per benchmark and one bar or dumbbell row per method. Each chart switches by its own width,
// so a narrow card on a laptop also gets the layout that fits.

let tip = null;

function tooltip() {
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'chart-tip';
    tip.hidden = true;
    tip.setAttribute('role', 'presentation');
    document.body.appendChild(tip);
  }
  return tip;
}

// data: { title, sub, rows: [{ name, text, tone, ours }] }. Each row is a colour key, the method
// and its value, laid out as a grid so every method gets its own line.
function showTip(data, x, y) {
  const t = tooltip();
  t.textContent = '';
  const head = el('div', 'tip-head');
  head.appendChild(el('b', '', data.title));
  if (data.sub) head.appendChild(el('span', 'tip-sub', data.sub));
  const rows = el('div', 'tip-rows');
  for (const r of data.rows) {
    const key = el('i', 'tip-key' + (r.ours ? ' ours' : ''));
    if (r.tone) key.dataset.tone = r.tone;
    rows.append(key, el('span', 'tip-name' + (r.ours ? ' ours' : ''), r.name), el('span', 'tip-val' + (r.ours ? ' ours' : ''), r.text));
  }
  t.append(head, rows);
  t.hidden = false;
  const rc = t.getBoundingClientRect();
  const left = Math.min(window.innerWidth - rc.width - 8, Math.max(8, x + 14));
  const top = y - rc.height - 12 < 8 ? y + 16 : y - rc.height - 12;
  t.style.left = `${left}px`;
  t.style.top = `${top}px`;
}

function hideTip() { if (tip) tip.hidden = true; }

function withTip(target, data, anchor) {
  target.addEventListener('pointermove', (e) => showTip(data, e.clientX, e.clientY));
  target.addEventListener('pointerleave', hideTip);
  target.addEventListener('focus', () => {
    const rc = anchor().getBoundingClientRect();
    showTip(data, rc.right, rc.top);
  });
  target.addEventListener('blur', hideTip);
}

// tooltip and screen-reader text of one benchmark: every method with its value
function tipOf(r, series, panel) {
  return {
    title: r.label,
    sub: panel || '',
    rows: r.values.map((v, k) => ({ name: series[k].name, text: v.text, tone: series[k].tone, ours: series[k].ours })),
  };
}

function describe(target, data) {
  target.tabIndex = 0;
  target.setAttribute('role', 'img');
  target.setAttribute('aria-label', `${data.sub ? `${data.sub}, ` : ''}${data.title}: ${data.rows.map((r) => `${r.name} ${r.text}`).join(', ')}`);
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// ---------------------------------------------------------------- horizontal bars
function bars(fig, table) {
  const metric = table.tHead ? table.tHead.rows[0].cells[1].textContent.trim() : '';
  const unit = /\(%\)$/.test(metric) ? '%' : '';  // "Accuracy (%)" shows as "Accuracy 59.7%"
  const metricName = metric.replace(/\s*\(%\)$/, '');
  const rows = [...table.tBodies[0].rows].map((tr) => ({
    name: tr.cells[0].textContent.trim(),
    text: tr.cells[1].textContent.trim(),
    value: parseFloat(tr.cells[1].textContent),
    ours: tr.hasAttribute('data-ours'),
    tone: tr.dataset.tone || '',
    group: tr.dataset.group || '',
  }));
  const scale = Number(fig.dataset.scale) || Math.max(...rows.map((r) => r.value));
  const box = el('div', 'hbars');
  let group = null;
  for (const r of rows) {
    if (r.group && r.group !== group) box.appendChild(el('div', 'hbar-group', r.group));
    group = r.group;
    const row = el('div', 'hbar' + (r.ours ? ' ours' : ''));
    if (r.tone) row.dataset.tone = r.tone;
    const data = { title: r.name, sub: r.group, rows: [{ name: metricName, text: r.text + unit, tone: r.tone, ours: r.ours }] };
    describe(row, data);
    const track = el('span', 'track');
    const fill = el('span', 'fill');
    fill.style.width = `${(Math.max(0, Math.min(1, r.value / scale)) * 100).toFixed(2)}%`;
    track.appendChild(fill);
    row.append(el('span', 'name', r.name), track);
    withTip(row, data, () => fill);
    box.appendChild(row);
  }
  table.after(box);
  if (fig.dataset.ref) {
    const line = el('i', 'ref-line');
    box.style.setProperty('--ref', String(Number(fig.dataset.ref) / scale));
    box.appendChild(line);
    const note = el('p', 'ref-note');
    note.append(el('i'), fig.dataset.refLabel || '');
    box.after(note);
  }
  watchWidth(fig, { stacked: 0, side: 0 });
}

// ---------------------------------------------------------------- shared parts of the vertical charts
function readSeries(table) {
  return [...table.tHead.rows[0].cells].slice(1).map((th) => ({
    name: th.textContent.trim(),
    tone: th.dataset.tone || '',
    ours: th.hasAttribute('data-ours'),
  }));
}

function readRows(table) {
  return [...table.tBodies[0].rows].map((tr) => ({
    label: tr.cells[0].textContent.trim(),
    panel: tr.cells[0].dataset.panel || '',
    scale: tr.cells[0].dataset.max ? scaleOf(tr.cells[0]) : null,
    values: [...tr.cells].slice(1).map((td) => ({ text: td.textContent.trim(), value: parseFloat(td.textContent) })),
  }));
}

function legend(series) {
  const box = el('div', 'chart-legend' + (series.every((s) => s.name.length <= 18) ? ' compact' : ''));
  for (const s of series) {
    const key = el('span', 'key' + (s.ours ? ' ours' : ''));
    if (s.tone) key.dataset.tone = s.tone;
    key.append(el('i'), s.name);
    box.appendChild(key);
  }
  return box;
}

// scale of a figure, or of a panel when its first cell carries data-min, data-max and data-ticks
function scaleOf(node) {
  const min = Number(node.dataset.min || 0);
  const max = Number(node.dataset.max);
  const ticks = (node.dataset.ticks || '').split(',').filter(Boolean);
  const y = (v) => Math.max(0, Math.min(1, (v - min) / (max - min))) * 100;
  return { ticks, y };
}

function yAxis(ticks, y) {
  const ax = el('div', 'v-axis');
  ax.setAttribute('aria-hidden', 'true');
  for (const t of ticks) {
    const s = el('span', '', t);
    s.style.bottom = `${y(Number(t)).toFixed(2)}%`;
    ax.appendChild(s);
  }
  return ax;
}

function gridLines(area, ticks, y) {
  for (const t of ticks) {
    const g = el('i', 'v-grid');
    g.style.bottom = `${y(Number(t)).toFixed(2)}%`;
    area.appendChild(g);
  }
}

function xLabel(r) {
  return el('span', 'v-xlabel', r.label);
}

// Switch layouts by the card's own width: panels side by side, panels stacked, or the narrow
// horizontal layout. `need` gives the widths (px) the vertical layouts need. Below NARROW every
// chart uses the narrow layout, so all charts on a phone look alike.
const NARROW = 400;

function watchWidth(fig, need) {
  const apply = () => {
    const cs = getComputedStyle(fig);
    const w = fig.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    if (!w) return;
    const narrow = w < Math.max(need.stacked, NARROW);
    fig.classList.toggle('is-narrow', narrow);
    fig.classList.toggle('stack-panels', !narrow && w < need.side);
  };
  apply();
  if ('ResizeObserver' in window) new ResizeObserver(apply).observe(fig);
  else window.addEventListener('resize', apply);
}

function narrowAxis(ticks, y, lead) {
  const ax = el('div', 'm-axis' + (lead ? ' lead' : ''));
  ax.setAttribute('aria-hidden', 'true');
  if (lead) ax.appendChild(el('span'));
  const sc = el('span', 'm-ticks');
  for (const t of ticks) {
    const s = el('span', '', t);
    s.style.left = `${y(Number(t)).toFixed(2)}%`;
    sc.appendChild(s);
  }
  ax.appendChild(sc);
  return ax;
}

// narrow layout of grouped columns: a label line, then one bar per method (values in the tooltip).
// One axis at the bottom, or one under each panel when the panels have their own scales.
function narrowColumns(series, panels, shared) {
  const box = el('div', 'm-chart');
  for (const p of panels) {
    const { y } = p;
    if (p.title) box.appendChild(el('div', 'm-panel-title', p.title));
    for (const r of p.rows) {
      const g = el('div', 'm-group');
      const data = tipOf(r, series, p.title);
      describe(g, data);
      withTip(g, data, () => g);
      g.appendChild(el('div', 'm-label', r.label));
      r.values.forEach((v, k) => {
        const s = series[k];
        const row = el('div', 'm-row' + (s.ours ? ' ours' : ''));
        if (s.tone) row.dataset.tone = s.tone;
        const track = el('span', 'm-track');
        const fill = el('i', 'm-fill');
        fill.style.width = `${y(v.value).toFixed(2)}%`;
        track.appendChild(fill);
        row.appendChild(track);
        g.appendChild(row);
      });
      box.appendChild(g);
    }
    if (!shared) box.appendChild(narrowAxis(p.ticks, p.y, false));
  }
  if (shared) box.appendChild(narrowAxis(shared.ticks, shared.y, false));
  return box;
}

// narrow layout of lollipops: name and dumbbell in two aligned columns (values in the tooltip)
function narrowLollipop(series, rows, ticks, y) {
  const box = el('div', 'm-chart');
  for (const r of rows) {
    const row = el('div', 'm-lrow');
    const data = tipOf(r, series);
    describe(row, data);
    withTip(row, data, () => row);
    const name = el('span', 'm-name', r.label);
    const track = el('span', 'm-ltrack');
    for (const t of ticks) {
      const g = el('i', 'm-grid');
      g.style.left = `${y(Number(t)).toFixed(2)}%`;
      track.appendChild(g);
    }
    const vals = r.values.map((v) => v.value);
    const stem = el('i', 'stem');
    stem.style.left = `${y(Math.min(...vals)).toFixed(2)}%`;
    stem.style.width = `${(y(Math.max(...vals)) - y(Math.min(...vals))).toFixed(2)}%`;
    track.appendChild(stem);
    r.values.forEach((v, k) => {
      const s = series[k];
      const dot = el('i', 'dot' + (s.ours ? ' ours' : ''));
      if (s.tone) dot.dataset.tone = s.tone;
      dot.style.left = `${y(v.value).toFixed(2)}%`;
      track.appendChild(dot);
    });
    row.append(name, track);
    box.appendChild(row);
  }
  box.appendChild(narrowAxis(ticks, y, true));
  return box;
}

// ---------------------------------------------------------------- grouped vertical bars
function columns(fig, table) {
  const series = readSeries(table);
  const rows = readRows(table);
  const shared = rows.some((r) => r.scale) ? null : scaleOf(fig);

  const panels = [];
  for (const r of rows) {
    if (!panels.length || r.panel) panels.push({ title: r.panel, rows: [], ...(r.scale || shared) });
    panels[panels.length - 1].rows.push(r);
  }

  const plot = el('div', 'v-plot');
  for (const p of panels) {
    const { ticks, y } = p;
    const panel = el('div', 'v-panel');
    panel.style.flexGrow = String(p.rows.length);
    if (p.title) panel.appendChild(el('div', 'v-panel-title', p.title));
    const body = el('div', 'v-body');
    body.appendChild(yAxis(ticks, y));
    const area = el('div', 'v-area');
    gridLines(area, ticks, y);
    const labels = el('div', 'v-xlabels');
    for (const r of p.rows) {
      const group = el('div', 'v-group');
      const data = tipOf(r, series, p.title);
      describe(group, data);
      r.values.forEach((v, k) => {
        const s = series[k];
        const bar = el('i', 'v-bar' + (s.ours ? ' ours' : ''));
        if (s.tone) bar.dataset.tone = s.tone;
        bar.style.height = `${y(v.value).toFixed(2)}%`;
        group.appendChild(bar);
      });
      withTip(group, data, () => group);
      area.appendChild(group);
      labels.appendChild(xLabel(r));
    }
    body.appendChild(area);
    panel.append(body, labels);
    plot.appendChild(panel);
  }
  table.after(legend(series), plot, narrowColumns(series, panels, shared));
  // each group needs room for its bars, plus the y axis. data-bar lowers the minimum bar width for
  // charts with many groups (for example 13 abnormalities), so they keep the vertical layout on desktop.
  const perGroup = series.length * (Number(fig.dataset.bar) || 18) + 16;
  const panelNeed = (p) => p.rows.length * perGroup + 38;
  const stacked = Math.max(...panels.map(panelNeed));
  watchWidth(fig, { stacked, side: panels.reduce((sum, p) => sum + panelNeed(p), 0) + 20 * (panels.length - 1) });
}

// ---------------------------------------------------------------- vertical lollipops (one comparison)
function lollipop(fig, table) {
  const series = readSeries(table);
  const rows = readRows(table);
  const { ticks, y } = scaleOf(fig);

  const plot = el('div', 'v-plot');
  const panel = el('div', 'v-panel');
  const body = el('div', 'v-body');
  body.appendChild(yAxis(ticks, y));
  const area = el('div', 'v-area');
  gridLines(area, ticks, y);
  const labels = el('div', 'v-xlabels');
  for (const r of rows) {
    const col = el('div', 'v-group lolli');
    const data = tipOf(r, series);
    describe(col, data);
    const vals = r.values.map((v) => v.value);
    const stem = el('i', 'stem');
    stem.style.bottom = `${y(Math.min(...vals)).toFixed(2)}%`;
    stem.style.height = `${(y(Math.max(...vals)) - y(Math.min(...vals))).toFixed(2)}%`;
    col.appendChild(stem);
    r.values.forEach((v, k) => {
      const s = series[k];
      const dot = el('i', 'dot' + (s.ours ? ' ours' : ''));
      if (s.tone) dot.dataset.tone = s.tone;
      dot.style.bottom = `${y(v.value).toFixed(2)}%`;
      col.appendChild(dot);
    });
    withTip(col, data, () => col);
    area.appendChild(col);
    labels.appendChild(xLabel(r));
  }
  body.appendChild(area);
  panel.append(body, labels);
  plot.appendChild(panel);
  table.after(legend(series), plot, narrowLollipop(series, rows, ticks, y));
  const need = rows.length * 60 + 38;
  watchWidth(fig, { stacked: need, side: need });
}

// ---------------------------------------------------------------- one bar width for a block of charts
const synced = new WeakSet();

function syncBars(box) {
  if (synced.has(box)) return;
  synced.add(box);
  const apply = () => {
    let w = 30;
    box.querySelectorAll('figure.chart.columns:not(.is-narrow) .v-group').forEach((g) => {
      const n = g.querySelectorAll('.v-bar').length;
      if (!n || !g.clientWidth) return;
      const cs = getComputedStyle(g);
      const inner = g.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      w = Math.min(w, (inner - (parseFloat(cs.columnGap) || 0) * (n - 1)) / n);
    });
    box.style.setProperty('--bar-max', `${Math.max(4, Math.floor(w))}px`);
  };
  apply();
  if ('ResizeObserver' in window) new ResizeObserver(apply).observe(box);
  else window.addEventListener('resize', apply);
}

export function renderCharts(root = document) {
  root.querySelectorAll('figure.chart').forEach((fig) => {
    if (fig.classList.contains('has-bars')) return;
    const table = fig.querySelector('table');
    if (!table || !table.tBodies.length) return;
    if (fig.classList.contains('columns')) columns(fig, table);
    else if (fig.classList.contains('lollipop')) lollipop(fig, table);
    else bars(fig, table);
    fig.classList.add('has-bars');
  });
  root.querySelectorAll('[data-same-bars]').forEach(syncBars);
}

window.addEventListener('scroll', hideTip, { passive: true });
