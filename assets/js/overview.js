// A task selector for the scientific overview. All examples use the project's own assets.
import { SAMPLING_ROUTES } from './prior-routes.js';

const TASKS = [
  {
    key: 'report', name: 'Report-to-volume generation', input: 'Radiology report',
    output: 'Generated CT / MRI', image: 'assets/img/concept/out_report.webp',
    outputViews: cubeFaces('report_out'),
    alt: 'Generated CT showing the findings described in a radiology report',
    caption: 'Generate CT volumes reflecting report-described findings.',
    setting: '“There is a mild pericardial effusion, up to 12 mm thick.”',
  },
  {
    key: 'mask', name: 'Mask-to-volume generation', input: 'Organ / tumor mask',
    inputViews: spriteViews('assets/img/views/m2i_a', [29, 19, 17], '_label'),  // the condition itself: body and organ labels
    inputImage: 'assets/img/concept/in_mask.webp', inputAlt: 'Organ segmentation mask used to guide CT generation',
    output: 'Generated CT / MRI', image: 'assets/img/concept/out_mask.webp',
    outputViews: spriteViews('assets/img/views/m2i_a', [29, 19, 17]),
    alt: 'Generated CT matching the supplied organ mask',
    caption: 'Generate CT volumes consistent with supplied segmentation masks.',
    setting: 'Organ / tumor segmentation mask.',
  },
  {
    key: 'translation', name: 'Modality translation', input: 'Source scan',
    inputImage: 'assets/img/concept/in_source.webp', inputAlt: 'Acquired source scan for modality translation',
    inputViews: cubeFaces('mr2ct_in'),
    output: 'Target modality', image: 'assets/img/concept/out_source.webp',
    outputViews: cubeFaces('mr2ct_out'),
    alt: 'Generated target modality from the acquired source scan',
    caption: 'Condition on an available scan to generate a target modality, MRI sequence or contrast phase.',
    setting: 'Head and neck MRI → CT.',
  },
  {
    key: 'treatment', name: 'Treatment simulation', input: 'Pre-treatment CT',
    inputImage: 'assets/img/concept/in_pre.webp', inputAlt: 'Pre-treatment CT used for virtual treatment simulation',
    inputViews: cubeFaces('tace_pre'),
    output: 'Virtual post-treatment CT', image: 'assets/img/concept/out_tace.webp',
    outputViews: cubeFaces('tace_virtual'),
    alt: 'Virtual post-treatment CT generated from the pre-treatment scan and treatment details',
    caption: 'Simulate post-treatment CT from pre-treatment CT and treatment details.',
    setting: 'TACE: pirarubicin 12 mg, lobaplatin 15 mg, lipiodol 5 mL.',
  },
];

// Schematic pretraining pairs reuse each representative scan on the denoising
// side. They explain the training flow, rather than report measured denoising results.
const PRETRAINING_EXAMPLES = [
  { key: 'chest-ct', input: 'Chest CT', prefix: 'pretrain_ct_0' },
  { key: 'abdomen-ct', input: 'Abdomen / pelvis CT', prefix: 'gen_abdomen_0' },
  { key: 'head-neck-ct', input: 'Head and neck CT', prefix: 'gen_hn_0' },
  { key: 'brain-mri', input: 'Brain MRI', prefix: 'pretrain_mr_0' },
].map(example => {
  const views = orthogonalViews(`assets/img/poster/extra/${example.prefix}`);
  return {
    ...example,
    name: 'Foundation pretraining',
    inputViews: views,
    inputAlt: `${example.input} representative volume illustrating a pretraining input`,
    output: 'Denoised volume',
    outputViews: views,
    alt: `${example.input} denoising schematic using the same representative volume, not a measured denoising result`,
    caption: 'Learn a shared generative prior from diverse 3D CT and MRI volumes.',
    setting: `${example.input} → denoised volume.`,
  };
});

let overviewCount = 0;
const SVG_NS = 'http://www.w3.org/2000/svg';

function inputMarkup(task, id) {
  if (task.key === 'report') return `<div class="mo-report" role="img" aria-label="Radiology report excerpt: There is a mild pericardial effusion, up to 12 mm thick." title="There is a mild pericardial effusion, up to 12 mm thick.">
    <svg viewBox="0 0 36 44" fill="none" aria-hidden="true" focusable="false">
      <path d="M7 2h15l7 7v33H7zM22 2v8h7"/>
      <path d="M12 16h12M12 21h12M12 26h9M12 31h12M12 36h7"/>
    </svg>
  </div>`;
  return volumeMarkup(id, { views: task.inputViews, slice: task.inputImage, alt: task.inputAlt });
}

function outputMarkup(task, id) {
  return volumeMarkup(id, { views: task.outputViews, slice: task.still || task.image, alt: task.alt });
}

// Axial, coronal and sagittal faces of a real volume, from tools/make_cubes.py.
function cubeFaces(name) {
  return ['axial', 'coronal', 'sagittal'].map(plane => `assets/img/concept/cube_${name}_${plane}.webp`);
}

function orthogonalViews(prefix, suffix = '') {
  return ['axial', 'coronal', 'sagittal'].map(plane => `${prefix}_${plane}${suffix}.webp`);
}

// Representative frame indices from data/showcase.json; select one tile per sprite.
function spriteViews(prefix, frames, suffix = '') {
  return orthogonalViews(prefix, suffix).map((src, i) => ({ src, frame: frames[i], cols: 6, rows: 6 }));
}

function volumeFace(view, transform) {
  if (typeof view === 'string') return `<image href="${view}" width="100" height="100" transform="${transform}"/>`;
  const x = (view.frame % view.cols) * 100;
  const y = Math.floor(view.frame / view.cols) * 100;
  return `<g transform="${transform}"><svg width="100" height="100" viewBox="${x} ${y} 100 100" overflow="hidden"><image href="${view.src}" width="${view.cols * 100}" height="${view.rows * 100}"/></svg></g>`;
}

function tokenMarkup(noisy = false) {
  const cells = Array.from({ length: 24 }, (_, i) => {
    const opacity = noisy ? .18 + ((i * 17 + 9) % 29) / 38 : .5 + Math.floor(i / 6) * .12;
    return `<i style="--token-opacity:${opacity.toFixed(2)}"></i>`;
  }).join('');
  return `<div class="mo-token-grid${noisy ? ' is-noisy' : ''}" aria-hidden="true">${cells}</div>`;
}

// The geometry is identical for every volume. Matched three-view examples show actual
// orthogonal slices; single-image examples use the original slice as an illustrative texture.
function volumeMarkup(id, options = {}) {
  const views = options.views || (options.slice ? [options.slice, options.slice, options.slice] : orthogonalViews('assets/img/poster/extra/pretrain_ct_0'));
  const alt = options.alt || '3D CT volume illustration using axial, coronal and sagittal views';
  return `<svg class="mo-scan-volume" viewBox="0 0 144 128" role="img" aria-labelledby="${id}-volume-title">
    <title id="${id}-volume-title">${alt}${options.slice && !options.views ? ' — illustrative cube textured with the representative slice, not orthogonal views' : ''}</title>
    ${volumeFace(views[0], 'matrix(.62 .24 -.5 .18 66 12)')}
    ${volumeFace(views[1], 'matrix(.62 .24 0 .62 16 30)')}
    ${volumeFace(views[2], 'matrix(.5 -.18 0 .62 78 54)')}
    <path d="M16 30 66 12 128 36 128 98 78 116 16 92Z M16 30 78 54 128 36 M78 54V116"/>
  </svg>`;
}

export function initOverview(root = document) {
  const components = [...root.querySelectorAll('.model-overview')];
  if (root.matches?.('.model-overview')) components.unshift(root);
  components.forEach(setupOverview);
}

function setupOverview(component) {
  if (component.dataset.overviewReady) return;
  component.dataset.overviewReady = 'true';
  const doc = component.ownerDocument;
  const win = doc.defaultView;
  const uid = `rw-overview-${++overviewCount}`;
  const pretraining = component.dataset.overview === 'pretraining';
  const tasks = pretraining ? PRETRAINING_EXAMPLES : TASKS;
  const heading = pretraining
    ? 'The human body.<br><span>A shared generative foundation.</span>'
    : 'Many tasks.<br><span>One generative framework.</span>';
  const description = pretraining
    ? 'Pretrained on 232,781 curated scans from 152 datasets across 23 countries, RadWorld learns a shared generative prior across anatomical regions and imaging modalities.'
    : 'CT and MRI tasks differ in the information available and the examination required. RadWorld brings scan generation, imaging translation and treatment simulation into a common formulation: generate a target 3D volume from the supplied conditions.';
  component.innerHTML = `
    ${component.previousElementSibling?.matches('.model-overview') ? `<a class="hero-scroll mo-next-story" href="#${uid}-title" aria-label="Continue to ${pretraining ? 'foundation pretraining' : 'the unified framework'}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></a>` : ''}
    <section class="mo-story mo-story-${pretraining ? 'foundation' : 'adaptation'}" aria-labelledby="${uid}-title">
    <header class="mo-heading mo-task-heading">
      <h2 id="${uid}-title">${heading}</h2>
      <p class="mo-bridge">${description}</p>
    </header>
    <div class="mo-diagram" role="group" aria-label="${pretraining ? 'Foundation pretraining with diverse 3D CT and MRI volumes' : 'Clinical information guiding 3D imaging simulation of the human body'}" data-rotation-paused="false">
      <svg class="mo-wires" aria-hidden="true" focusable="false"></svg>
      <div class="mo-task-story" aria-label="Task examples">
        <div class="mo-task-window" aria-hidden="true"><div class="mo-task-track">
          ${(pretraining ? tasks.slice(0, 1) : tasks).map(task => `<div class="mo-task-name">${task.name}</div>`).join('')}
        </div></div>
        <div class="mo-details" id="${uid}-panel" role="group" aria-label="${tasks[0].name}">
          <p class="mo-caption">${tasks[0].caption}</p>
          ${pretraining ? '' : `<p class="mo-task-setting"><em>${tasks[0].setting}</em></p>`}
        </div>
      </div>
      <div class="mo-ports mo-inputs" role="group" aria-label="Inputs">
        ${tasks.map((task, i) => `<div class="mo-port mo-input${pretraining || i === 0 ? ' is-active' : ''}" data-task="${task.key}" ${pretraining ? `role="group" aria-label="${task.input}"` : `role="button" tabindex="0" aria-label="Show ${task.name}: ${task.input}" aria-pressed="${i === 0}"`}>
          <div class="mo-port-content">${inputMarkup(task, `${uid}-input-${task.key}`)}</div>
          <div class="mo-port-label">${task.input}${task.key === 'treatment' ? '<small>+ treatment details</small>' : ''}</div>
        </div>`).join('')}
      </div>
      <div class="mo-core" role="group" aria-label="Patch tokens through RadWorld">
        <div class="mo-token-stage mo-input-tokens">${tokenMarkup()}</div>
        <svg class="mo-core-arrow" viewBox="0 0 40 16" aria-hidden="true"><path d="M1 8h36m-6-6 6 6-6 6"/></svg>
        <div class="mo-model"><h3>RadWorld</h3></div>
        <svg class="mo-core-arrow" viewBox="0 0 40 16" aria-hidden="true"><path d="M1 8h36m-6-6 6 6-6 6"/></svg>
        <div class="mo-token-stage mo-output-tokens">${tokenMarkup()}</div>
      </div>
      <figure class="mo-prior${pretraining ? '' : ' mo-prior-task'}"${pretraining ? '' : ' role="img"'}><img src="assets/img/concept/pretraining-prior.svg" width="570" height="270" alt="${pretraining ? 'Conceptual multi-peak Gaussian surface illustrating the shared generative prior over CT and MRI volumes; not a measured density.' : ''}" decoding="async">${pretraining ? '' : '<svg class="mo-sampling" viewBox="15 -35 570 270" aria-hidden="true" focusable="false"></svg>'}</figure>
      <div class="mo-ports mo-outputs" role="group" aria-label="Outputs">
        ${tasks.map((task, i) => `<div class="mo-port mo-output${pretraining || i === 0 ? ' is-active' : ''}" data-task="${task.key}" ${pretraining ? `role="group" aria-label="${task.input}"` : `role="button" tabindex="0" aria-label="Show ${task.name}: ${task.input}" aria-pressed="${i === 0}"`}>
          <div class="mo-port-content">${outputMarkup(task, `${uid}-output-${task.key}`)}</div>
          <div class="mo-port-label">${task.output}</div>
        </div>`).join('')}
      </div>
    </div>
    </section>`;

  const diagram = component.querySelector('.mo-diagram');
  const wires = component.querySelector('.mo-wires');
  const model = component.querySelector('.mo-model');
  const inputs = [...component.querySelectorAll('.mo-input')];
  const outputs = [...component.querySelectorAll('.mo-output')];
  const details = component.querySelector('.mo-details');
  const caption = component.querySelector('.mo-caption');
  const taskSetting = component.querySelector('.mo-task-setting em');
  const taskTrack = component.querySelector('.mo-task-track');
  const reducedMotion = win.matchMedia('(prefers-reduced-motion: reduce)');
  let selected = 0;
  let rotationPaused = false;
  function drawSampling() {
    if (pretraining) return;
    const task = tasks[selected];
    const route = SAMPLING_ROUTES[task.key];
    const prior = component.querySelector('.mo-prior-task');
    prior.dataset.samplingTask = task.key;
    prior.setAttribute('aria-label', `${task.name}: an illustrative conditional sampling trajectory arriving at a distinct point on the shared generative prior, not a measured model trajectory.`);
    prior.querySelector('.mo-sampling').innerHTML = `
      <path class="mo-sampling-underlay" d="${route.trail}"/>
      <path class="mo-sampling-trail" d="${route.trail}"/>
      <circle class="mo-sampling-origin" cx="${route.startX}" cy="${route.startY}" r="2.8"/>
      <circle class="mo-sampling-target" cx="${route.x}" cy="${route.y}" r="2.2"/>
      ${reducedMotion.matches ? '' : `<g class="mo-sampling-motion"><circle r="2"/><animateMotion path="${route.path}" dur="2.8s" repeatCount="indefinite" calcMode="paced"/><animate attributeName="opacity" values="${route.visibilityValues}" keyTimes="${route.visibilityTimes}" calcMode="discrete" dur="2.8s" repeatCount="indefinite"/></g>`}`;
  }
  if (!pretraining) inputs.forEach((input, index) => {
    [input, outputs[index]].forEach(port => {
      function chooseTask() {
        rotationPaused = true;
        diagram.dataset.rotationPaused = 'true';
        selectTask(index);
      }
      port.addEventListener('click', chooseTask);
      port.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        chooseTask();
      });
    });
  });

  function drawWires() {
    const d = diagram.getBoundingClientRect();
    const m = model.getBoundingClientRect();
    const inTokens = component.querySelector('.mo-input-tokens').getBoundingClientRect();
    const outTokens = component.querySelector('.mo-output-tokens').getBoundingClientRect();
    if (!d.width || !d.height) return;
    const compact = win.matchMedia('(max-width: 699px)').matches;
    wires.setAttribute('viewBox', `0 0 ${d.width} ${d.height}`);
    wires.replaceChildren();
    function line(shape, side, active = false) {
      const path = doc.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', shape);
      path.setAttribute('class', `mo-wire mo-wire-${side}${active ? ' is-active' : ''}`);
      wires.append(path);
    }
    function flow(shape) {
      if (reducedMotion.matches) return;
      // Travel in the path's direction: input → tokens → model → tokens → output.
      for (let i = 0; i < 2; i++) {
        const pulse = doc.createElementNS(SVG_NS, 'g');
        pulse.setAttribute('class', 'mo-flow-pulse');
        for (const [radius, opacity] of [[5, .14], [2.1, .95]]) {
          const dot = doc.createElementNS(SVG_NS, 'circle');
          dot.setAttribute('r', radius);
          dot.setAttribute('opacity', opacity);
          pulse.append(dot);
        }
        const motion = doc.createElementNS(SVG_NS, 'animateMotion');
        motion.setAttribute('path', shape);
        motion.setAttribute('dur', '2.8s');
        motion.setAttribute('begin', `${-i * 1.4}s`);
        motion.setAttribute('repeatCount', 'indefinite');
        motion.setAttribute('calcMode', 'paced');
        pulse.append(motion);
        wires.append(pulse);
      }
    }
    if (compact && pretraining) {
      const centerX = m.left + m.width / 2 - d.left;
      const top = inTokens.top - d.top - 4;
      const inputBottom = component.querySelector('.mo-inputs').getBoundingClientRect().bottom - d.top;
      const inputBus = inputBottom + (top - inputBottom) / 2;
      const outputStart = outTokens.bottom - d.top + 4;
      const outputTop = component.querySelector('.mo-outputs').getBoundingClientRect().top - d.top;
      const outputBus = outputStart + (outputTop - outputStart) / 2;
      inputs.forEach((input, index) => {
        const a = input.getBoundingClientRect();
        const b = outputs[index].querySelector('.mo-port-content').getBoundingClientRect();
        const ax = a.left + a.width / 2 - d.left;
        const ay = a.bottom - d.top + 3;
        const bx = b.left + b.width / 2 - d.left;
        const by = b.top - d.top - 4;
        line(`M ${ax} ${ay} V ${inputBus} H ${centerX} V ${top}`, 'in', true);
        line(`M ${centerX} ${outputStart} V ${outputBus} H ${bx} V ${by}`, 'out', true);
        line(`M ${bx - 3} ${by - 4} L ${bx} ${by} L ${bx + 3} ${by - 4}`, 'out', true);
        flow(`M ${ax} ${ay} V ${inputBus} H ${centerX} V ${outputBus} H ${bx} V ${by}`);
      });
      return;
    }
    if (compact) {
      const a = inputs[selected].getBoundingClientRect();
      const b = outputs[selected].querySelector('.mo-port-content').getBoundingClientRect();
      const x = m.left + m.width / 2 - d.left;
      const top = inTokens.top - d.top - 4;
      const bottom = b.top - d.top - 4;
      line(`M ${x} ${a.bottom - d.top + 3} V ${top}`, 'in', true);
      line(`M ${x} ${outTokens.bottom - d.top + 4} V ${bottom}`, 'out', true);
      line(`M ${x - 3} ${top - 4} L ${x} ${top} L ${x + 3} ${top - 4}`, 'in', true);
      line(`M ${x - 3} ${bottom - 4} L ${x} ${bottom} L ${x + 3} ${bottom - 4}`, 'out', true);
      flow(`M ${x} ${a.bottom - d.top + 3} V ${bottom}`);
      return;
    }
    const centerY = m.top + m.height / 2 - d.top;
    const left = inTokens.left - d.left - 4;
    const right = outTokens.right - d.left + 4;
    const ports = inputs.map((input, i) => {
      const a = input.querySelector('.mo-port-content').getBoundingClientRect();
      const b = outputs[i].querySelector('.mo-port-content').getBoundingClientRect();
      return { i, inputX: a.right - d.left + 4, inputY: a.top + a.height / 2 - d.top,
        outputX: b.left - d.left - 4, outputY: b.top + b.height / 2 - d.top };
    });
    const inBus = (Math.max(...ports.map(p => p.inputX)) + left) / 2;
    const outBus = (right + Math.min(...ports.map(p => p.outputX))) / 2;
    line(`M ${inBus} ${ports[0].inputY} V ${ports.at(-1).inputY} M ${inBus} ${centerY} H ${left}`, 'in');
    line(`M ${right} ${centerY} H ${outBus} M ${outBus} ${ports[0].outputY} V ${ports.at(-1).outputY}`, 'out');
    ports.forEach(p => {
      line(`M ${p.inputX} ${p.inputY} H ${inBus}`, 'in');
      line(`M ${outBus} ${p.outputY} H ${p.outputX}`, 'out');
    });
    const activePorts = pretraining ? ports : [ports[selected]];
    activePorts.forEach(active => {
      line(`M ${active.inputX} ${active.inputY} H ${inBus} V ${centerY} H ${left}`, 'in', true);
      line(`M ${right} ${centerY} H ${outBus} V ${active.outputY} H ${active.outputX}`, 'out', true);
      line(`M ${active.outputX - 4} ${active.outputY - 3} L ${active.outputX} ${active.outputY} L ${active.outputX - 4} ${active.outputY + 3}`, 'out', true);
      flow(`M ${active.inputX} ${active.inputY} H ${inBus} V ${centerY} H ${outBus} V ${active.outputY} H ${active.outputX}`);
    });
    line(`M ${left - 4} ${centerY - 3} L ${left} ${centerY} L ${left - 4} ${centerY + 3}`, 'in', true);
  }

  function selectTask(index) {
    selected = (index + tasks.length) % tasks.length;
    const task = tasks[selected];
    if (!pretraining) taskTrack.style.transform = `translateY(${-selected * 100 / tasks.length}%)`;
    inputs.forEach((input, i) => {
      inputs[i].classList.toggle('is-active', i === selected);
      outputs[i].classList.toggle('is-active', i === selected);
      inputs[i].setAttribute('aria-pressed', String(i === selected));
      outputs[i].setAttribute('aria-pressed', String(i === selected));
    });
    details.setAttribute('aria-label', task.name);
    caption.textContent = task.caption;
    taskSetting.textContent = task.setting;
    drawSampling();
    drawWires();
  }

  component.querySelectorAll('img[data-fallback]').forEach((img) => {
    img.addEventListener('error', () => { img.src = img.dataset.fallback; }, { once: true });
  });
  reducedMotion.addEventListener('change', drawWires);
  reducedMotion.addEventListener('change', drawSampling);
  if (win.ResizeObserver) new win.ResizeObserver(drawWires).observe(diagram);
  else win.addEventListener('resize', drawWires, { passive: true });
  if (pretraining) { drawWires(); return; }
  drawSampling();
  let inView = false;
  if (win.IntersectionObserver) {
    const visibility = new win.IntersectionObserver(entries => {
      inView = entries[0].isIntersecting;
    }, { threshold: .3 });
    visibility.observe(diagram);
  } else inView = true;
  const rotation = win.setInterval(() => {
    if (!component.isConnected) { win.clearInterval(rotation); return; }
    if (rotationPaused || !inView || doc.hidden || reducedMotion.matches) return;
    selectTask(selected + 1);
  }, 3000);
  drawWires();
}
