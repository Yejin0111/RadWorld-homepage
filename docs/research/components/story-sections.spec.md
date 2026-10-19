# Centered story sections

Simulation and Synthetic data use the same centered header width, concise lead, focused overview and neutral pill actions. The shared stylesheet is `story-sections.css`; interactions live in `story-sections.js`.

Simulation retains the two original patient triplets and automatic case cycling. Captions are centered. Treatment details are a native disclosure below each triplet. Opening details pauses cycling through the existing carousel guard; closing allows it to resume. Regimens and single-line drug values are unchanged.

Downstream applications presents four equal centered task cards in a two-column grid (one column on phones): Classification, Tumor segmentation, Report generation and Survival prediction. Each card has a task title, concise description and View results; overview metric callouts are omitted. View results reveals only the matching existing chart, with the 2:1 synthetic-to-real ratio stated. The three original benchmark tables are byte-for-byte preserved; original chart labels, axes, legends and tooltips remain. Baselines use neutral tones and RadWorld uses the shared pale blue. A Close action returns focus to the relevant card. Chart sizing refreshes on reveal.

Initial overview panels are collapsed. No new quantitative results, images or performance claims are generated.

Report generation uses one metric view at a time (BLEU-2 by default). A centered, neutral metric selector switches between BLEU-2, ROUGE-L, METEOR and GREEN without expanding the page. Each view preserves its three regions, original scale, four methods and tooltips. Desktop and compact mobile views switch together; the original source table remains intact. Other benchmark charts are unchanged.

Survival prediction restores the original two-cohort C-index table from the previous Simulation section, including all four input settings and original values. It is mutually exclusive with the other result panels. The original Kaplan–Meier plots and hazard-ratio annotations remain behind a native View survival curves disclosure, collapsed initially. Both curves share a row on wide screens and stack on phones. The overview section keeps its #synthetic anchor for existing links. No survival results are added to the visual Simulation gallery.

The application header now reads Generate scans. Support downstream tasks. Its description distinguishes synthetic-data augmentation for classification/segmentation/report generation from virtual-image inputs for survival prediction. Each result figure uses a concise task + performance title. Original source tables, metrics, scales and disclosures remain unchanged.

Shared chart tooltips live under document.body. On pointer or keyboard display, they inherit the source chart's resolved --tone-1/2/3 and --rw palette explicitly. Legend keys, desktop bars, compact mobile bars and tooltip keys must match, including the pale-blue virtual post-TACE CT series; no chart data is changed.
