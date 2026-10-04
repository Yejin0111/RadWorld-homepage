// Kaplan-Meier curves for the treatment section, drawn from data/km.json (built by tools/build_km.py
// from the survival model's cross-validation results). Each <figure class="km" data-cohort="...">
// gets a legend, a step plot of the high- and low-risk groups and its axes.

const NS = 'http://www.w3.org/2000/svg';
const Y_TICKS = [0, 0.2, 0.4, 0.6, 0.8, 1.0];

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// step path in a 0..100 box: x in months mapped to [0, xmax], survival 0..1 mapped upwards
function stepPath(group, xmax) {
  const X = (t) => (Math.min(t, xmax) / xmax) * 100;
  const Y = (s) => (1 - s) * 100;
  let d = `M0 ${Y(1)}`;
  let s = 1;
  for (const [t, v] of group.steps) {
    if (t > xmax) break;
    d += ` H${X(t).toFixed(2)} V${Y(v).toFixed(2)}`;
    s = v;
  }
  return `${d} H${X(group.end).toFixed(2)}`;
}

function draw(fig, c) {
  const xmax = c.ticks[c.ticks.length - 1];
  const legend = el('div', 'chart-legend');
  for (const [risk, label] of [['high', 'High risk'], ['low', 'Low risk']]) {
    const key = el('span', 'key');
    key.dataset.risk = risk;
    key.append(el('i'), label);
    legend.appendChild(key);
  }

  const body = el('div', 'km-body');
  const yaxis = el('div', 'km-yaxis');
  yaxis.setAttribute('aria-hidden', 'true');
  const plot = el('div', 'km-plot');
  for (const v of Y_TICKS) {
    const lab = el('span', '', v.toFixed(1));
    lab.style.bottom = `${v * 100}%`;
    yaxis.appendChild(lab);
    if (v > 0) {
      const g = el('i', 'v-grid');
      g.style.bottom = `${v * 100}%`;
      plot.appendChild(g);
    }
  }
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Kaplan-Meier curves of progression-free survival in cohort ${fig.dataset.cohort}, high risk (${c.high.n} patients) and low risk (${c.low.n} patients)`);
  for (const risk of ['low', 'high']) {
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('class', risk);
    path.setAttribute('d', stepPath(c[risk], xmax));
    svg.appendChild(path);
  }
  plot.appendChild(svg);
  const xaxis = el('div', 'km-xaxis');
  xaxis.setAttribute('aria-hidden', 'true');
  for (const t of c.ticks) {
    const lab = el('span', '', String(t));
    lab.style.left = `${(t / xmax) * 100}%`;
    xaxis.appendChild(lab);
  }
  body.append(yaxis, plot, xaxis, el('div', 'km-axis-title', 'Months'));
  fig.querySelector('figcaption').after(legend, body);
}

export async function renderKM(root = document) {
  const figs = [...root.querySelectorAll('figure.km')];
  if (!figs.length) return;
  let data;
  try {
    data = await (await fetch('data/km.json')).json();
  } catch {
    return;
  }
  for (const fig of figs) {
    const c = data[fig.dataset.cohort];
    if (c && !fig.querySelector('.km-plot')) draw(fig, c);
  }
}
