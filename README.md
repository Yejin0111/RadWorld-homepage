# RadWorld project page

Static project page for *A World Foundation Model for 3D Tomographic Medical Imaging*.
Plain HTML, CSS and JavaScript. No build step, no external CDN and no web fonts, so the page
also loads in mainland China.

## Preview

```bash
python3 tools/serve.py 8000
# open http://localhost:8000
```

For a private review from another device, run `python3 tools/serve.py 8767 --token SECRET` and
`cloudflared tunnel --url http://127.0.0.1:8767`, then share `https://<tunnel>/?k=SECRET`. Requests
without the key get 403, and the key is kept in a cookie after the first visit.

`tools/serve.py` tells the browser to revalidate every file. With `python3 -m http.server` the
browser can keep an old `style.css` and old scripts after an edit and draw the new `index.html`
with them, which scrambles the layout until a hard reload (Cmd+Shift+R).

The page fetches its data and the quiz volumes, so opening `index.html` as a file shows a notice instead of the quiz.

## What to edit

| Change | File |
|---|---|
| Links, preprint or published state, arXiv id, journal details | `assets/js/site-config.js` |
| Page text | `index.html` |
| Styles | `assets/css/style.css` |
| Which volumes appear, windows, captions | `tools/prepare_assets.py` (then rebuild) |
| World-model figure under the title | `index.html` (`figure.wm`), images from `tools/make_concept.py` |
| Generation slides (cases, inputs, views) | `tools/make_views.py`, which writes `data/showcase.json` |
| Translation slide images | `tools/make_translation.py` |

The hero shows the title, the authors and links, then the world-model figure: five kinds of clinical
information (a radiology report, an organ mask, a tumor mask, a source modality, a pre-treatment CT
with procedural variables), RadWorld, the scan it generated from each, and what the scans are for. The
images are plain scans, without the figures' arrows or zoomed views. They come from the paper's figures
where it has them (Figures 2e, 2f, 4b and 5f). The organ-mask pair is the page's own case.
`assets/js/concept.js` draws the RadWorld band (the learned distribution as ridgelines, one picked
point per input, as in Figure 1b) and the arrows. Below 720 px the band runs down the middle, with the
inputs on its left and the scans on its right, and the ridgelines turn with it. The strip of generated
scans follows.

Generation, Translation and Treatment are carousels (`assets/js/carousel.js`): numbered tabs, previous
and next buttons (beside the slide on wide screens, next to the tabs on phones), swipe on phones and the
arrow keys on the tabs. On wide screens a carousel keeps the height of its tallest slide, so the page
does not move when the slide changes. Each slide is one task with the same layout as the others:
- Generation (`assets/js/showcase.js`): the input (the request, a sentence of the report or the organ
  mask) and three views of the generated volume, case chips above, the task's chart below. Each view
  opens on a chosen slice and steps through the volume as the pointer moves across it (dragging on
  touch screens). CT is shown over its whole range (-1000 to 1000 HU), without a window. The report
  cases are the four of Figure 2e, opening on the figure's slice with its arrows, and keep the figure's
  window, which their findings need. On the organ-mask slide the mask is blended onto the CT while the pointer is on a view (a tap
  on touch screens), and the input card shows the mask at the same axial slice.
- Translation: input, RadWorld and the real scan at one slice, then two charts side by side whose
  titles, legends and plots line up: whole-volume MAE, PSNR and MS-SSIM against the specialized models,
  and one chart of what the translation is for (Hounsfield-unit profile, reader study or segmentation).

`status: 'preprint'` shows the arXiv button and an arXiv BibTeX entry. `status: 'published'` shows
the journal button and a journal BibTeX entry built from `journal`.

The charts are plain tables in `index.html` (`<figure class="chart">`). `assets/js/charts.js` draws
them and hides the table, so a number is edited in one place. Colours follow the paper's figures:
compared methods get `data-tone="1"`, `"2"` or `"3"` (light to dark periwinkle, in the paper's order)
and RadWorld gets `data-ours` (pink). Class `columns` draws grouped vertical bars for several methods
on several benchmarks (`data-min`, `data-max`, `data-ticks`, `data-panel` on a row to start a panel),
class `lollipop` draws a single comparison across many categories, and a plain `chart` draws
horizontal bars. Charts carry no value labels: hovering, focusing or tapping a benchmark shows a
tooltip with one line per method. A chart narrower than its vertical layout needs (phones) switches
to horizontal rows, and `data-bar="14"` lets a chart with many groups use thinner bars before it switches.
`data-min`, `data-max` and `data-ticks` on a panel's first cell give that panel its own scale (one panel
per metric, as in Figure 3c). Charts inside an element with `data-same-bars` share one bar width, set
by the chart with the narrowest groups, so a chart with fewer groups gets wider gaps instead of wider bars.
`data-by="method"` compares methods on one setting: one panel per row (one metric each, named under its
bars), as in the translation slides. Class `lines` draws one line per method (retrieval curves and
Hounsfield-unit profiles), with `data-x="linear"` for numeric positions and one `<table data-variant>`
per switchable view (Recall@8 and Recall@16). A row label with `data-full` shows the full name in the
tooltip (the cancer abbreviations of Figure 3b). `data-narrow="300"` lets a chart in a small card
keep the vertical layout down to that width on wide screens (phones always get the horizontal rows).
`data-src` names the chart for `tools/check_charts.py`, so titles can be reworded without touching the checks.

The page describes data by body region and disease, without dataset names or sample sizes
(`tools/check_numbers.py` enforces this). The source datasets are credited once, under Image
credits in the footer, as their licenses require.

## Rebuilding assets

```bash
python3 tools/prepare_assets.py         # volumes, posters, teaser, data/gallery.json, data/turing.json
python3 tools/prepare_assets.py --only report,teaser   # rebuild part of it
python3 tools/make_social.py            # 1200x630 social preview
python3 tools/make_concept.py           # images of the world-model figure (paper figures, Figure 2f volumes, TACE crops)
python3 tools/make_views.py             # Generation slides: slice sprites, Figure 2e arrows, mask overlays, data/showcase.json
python3 tools/make_translation.py       # Translation slides: slices of Figure 4b and Extended Data Figure 5
python3 tools/build_km.py               # data/km.json, Kaplan-Meier curves of Figure 5e (needs the Overleaf folder)
python3 tools/check_numbers.py          # every number on the page must appear in the manuscript
```

Requirements: Python 3.9+, numpy, nibabel, Pillow, PyMuPDF, and pdftotext (poppler) for the checks.
The source folders are set at the top of `tools/prepare_assets.py`.

Volumes are stored as uint8 in RAS orientation. CT uses a piecewise-linear encoding
(`CT_RAW`/`CT_HU`) that keeps 2.8 HU steps between -200 and 300 HU. The manifest carries the
encoding, so window presets are defined in HU.

## Checking the page

```bash
python3 tools/check_numbers.py   # numbers must appear in the compiled manuscript or the text of its figures,
                                 # no semicolons or em dashes, no dataset names or sample sizes outside the credits
python3 tools/check_charts.py    # every chart cell must match its exact table cell, figure source data or
                                 # Results sentence, each chart title's claim must hold in every row, and the
                                 # TACE treatment details must match Figure 5f
python3 tools/test_page.py       # Chromium, WebKit and Firefox, desktop and phone sizes (a few minutes)
```

`test_page.py` starts its own server and checks the figure under the title, the carousels (tabs,
buttons, swipe, one height, images at one size), the Generation case chips, the charts and their
tooltips, the side-by-side charts lining up, plays the quiz and tries each `site-config.js` setting.
It also covers earlier bugs (a held key or a quick second click answering unseen quiz cases).

## Where the samples come from

| Section | Source |
|---|---|
| Whole-volume generation | `pretrain` and `pretrain_mr` demos, seeds 1995, 7 and 42, best case per region picked by eye. The request tags (scan type, body regions) come from the release's `examples/pretrain*.json` |
| Reports to CT | the four report-guided volumes of Figure 2e (`~/Desktop/生成工作材料/visualization`), at the figure's slices and window, with its arrows read from `figure2.pdf`. The reports are CT-RATE text that may not be redistributed, so the page gives only the sentence with the main finding, in our own words and shown as an excerpt between ellipses (`REPORT_CASES` in `tools/make_views.py`) |
| Translation | CBCT, MR and T1CE: the slices of Figure 4b and Extended Data Figure 5 (`resources/codes/figure4/data/modality_transfer_qualitative`), with their Hounsfield-unit profiles. Contrast phases: the `ct_arterial` demo output with its acquired arterial phase aligned by `tools/model_grid.py` |
| Visual Turing test | cases from the reader study, from datasets that allow redistribution. Per tumor type, the synthetic cases that most of the six readers judged real and real cases that all of them judged real (`reader_votes` in `tools/prepare_assets.py`) |
| Treatment simulation | image panel cropped from Figure 5f of the paper, with the treatment details printed there (age and sex left out) |
| Hero strip | axial sweeps through gallery volumes (`build_teaser`) |

## Adding samples from the GPU server

1. On the server, inside the code release with weights and demo data unpacked:
   `bash tools/server/generate_samples.sh /path/to/RadWorld-code /path/to/tools/server`
2. Copy `outputs_homepage/` to `~/Desktop/radworld_server_outputs/`.
3. Add entries to `EXTRA_CASES` in `tools/prepare_assets.py` (two commented examples are there),
   then run `python3 tools/prepare_assets.py --only extra`. A case whose `id` matches a placeholder
   in `PENDING` replaces that placeholder.

`tools/server/custom_reports_chest.json` holds report prompts written by the authors, so the page
can show the full input text next to the generated volume.

## Deploying

The site is served by GitHub Pages from the `main` branch of this repository, at
https://yejin0111.github.io/RadWorld-homepage/. Every push to `main` redeploys it within a minute or two. `.nojekyll` makes Pages
serve the files as they are, without a Jekyll build. The deployed files are about 120 MB, mostly
volumes, and no file is larger than 6 MB. If the address changes (for example a custom domain),
update the canonical link, `og:url`, `og:image` and `twitter:image` in `index.html`.

Before announcing the page: fill the links in `assets/js/site-config.js` (arXiv, code, weights) and
run the three checks above.

## Data on this page

Volumes shown in the viewers and in the visual Turing test are derived from public datasets and
are shared under their licenses, credited under Image credits in the footer (built by `fillCredits`
in `assets/js/main.js` from the `source` of each case). The per-case `credit` strings stay in
`data/gallery.json` for the record but are not shown. CT-RATE report text is not reproduced. The T1CE
slide shows the BraTS 2024 case of Extended Data Figure 5a as static images only, credited in the footer
(`FIGURE_SOURCES` in `assets/js/main.js`). Gzip decoding of the quiz volumes falls back to fflate (MIT),
whose license ships in `assets/vendor/`.
