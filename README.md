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

The viewers fetch volumes, so opening `index.html` as a file shows a notice instead of the viewers.

## What to edit

| Change | File |
|---|---|
| Links, preprint or published state, arXiv id, journal details | `assets/js/site-config.js` |
| Page text | `index.html` |
| Styles | `assets/css/style.css` |
| Which volumes appear, windows, captions | `tools/prepare_assets.py` (then rebuild) |

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
by the chart with the narrowest groups, so a chart with fewer groups gets wider gaps instead of wider bars. `data-src` names the chart for `tools/check_charts.py`, so titles can be
reworded without touching the checks.

The page describes data by body region and disease, without dataset names or sample sizes
(`tools/check_numbers.py` enforces this). The source datasets are credited once, under Image
credits in the footer, as their licenses require.

## Rebuilding assets

```bash
python3 tools/prepare_assets.py         # volumes, posters, teaser, data/gallery.json, data/turing.json
python3 tools/prepare_assets.py --only report,teaser   # rebuild part of it
python3 tools/make_social.py            # 1200x630 social preview
python3 tools/build_km.py               # data/km.json, Kaplan-Meier curves of Figure 5e (needs the Overleaf folder)
python3 tools/check_numbers.py          # every number on the page must appear in the manuscript
```

Requirements: Python 3.9+, numpy, nibabel, Pillow, PyMuPDF. The source folders are set at the top
of `tools/prepare_assets.py`.

Volumes are stored as uint8 in RAS orientation. CT uses a piecewise-linear encoding
(`CT_RAW`/`CT_HU`) that keeps 2.8 HU steps between -200 and 300 HU. The manifest carries the
encoding, so window presets are defined in HU.

## Checking the page

```bash
python3 tools/check_numbers.py   # numbers must appear in the compiled manuscript, no semicolons or em dashes,
                                 # no dataset names or sample sizes outside the image credits
python3 tools/check_charts.py    # every chart cell must match its exact table cell or Results sentence,
                                 # and each chart title's claim must hold in every row
python3 tools/test_page.py       # Chromium, WebKit and Firefox, desktop and phone sizes (a few minutes)
```

`test_page.py` starts its own server, loads every viewer and checks that the canvases contain
image data, opens the 3D dialog, plays the quiz, opens gallery cases and tries each
`site-config.js` setting. It also covers earlier bugs (a held key or a quick second click
answering unseen quiz cases, dialogs closing after a drag, two 3D volumes stacking).

## Where the samples come from

| Section | Source |
|---|---|
| Whole-volume generation | `pretrain` and `pretrain_mr` demos, seeds 1995, 7 and 42, best case per region picked by eye |
| Reports to CT | report-guided demo outputs of the code release (`outputs/t2i_chest`, `outputs/t2i_abdomen`), cases kept only when the output visibly shows the main findings. Their prompts are dataset reports that may not be redistributed, so the page lists only the main findings, written by the authors (`RELEASE_REPORT_CASES` in `tools/prepare_assets.py`) |
| Translation | `cbct2ct`, `mr2ct`, `ct_arterial` and `ct_venous` demo outputs, with the acquired scan of the same patient resampled onto the model grid by `tools/model_grid.py` |
| Visual Turing test | cases from the reader study, from datasets that allow redistribution |
| Treatment simulation | image panel cropped from Figure 5f of the paper |
| Hero strip | sweeps through gallery volumes (`build_teaser`) and a 3D rendering (`tools/capture_3d_teaser.py`) |

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

Any static host works. Deploy `index.html`, `assets/` and `data/`. The `tools/` folder is only needed
to rebuild the assets and refers to local source folders, so it can stay out of the public copy.
The deployed files are about 140 MB, mostly volumes, and no file is larger than 6 MB.
GitHub Pages is the simplest option. For readers in mainland China, a custom domain on GitHub
Pages is usually reachable, and a mirror on a mainland host needs an ICP filing.
Before going public: fill the links, set the canonical URL and an absolute
`og:image` in `index.html`, and run `python3 tools/check_numbers.py`.

## Data on this page

Volumes shown in the viewers and in the visual Turing test are derived from public datasets and
are shared under their licenses, credited under Image credits in the footer (built by `fillCredits`
in `assets/js/main.js` from the `source` of each case). The per-case `credit` strings stay in
`data/gallery.json` for the record but are not shown. CT-RATE report text is not reproduced.
The 3D rendering uses NiiVue (BSD-2-Clause) and gzip decoding falls back to fflate (MIT). Their
license files ship next to them in `assets/vendor/`.
