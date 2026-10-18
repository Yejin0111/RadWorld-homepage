# Translation cards

Four task slides retain the original flat Input / RadWorld / Ground truth comparisons. All performance charts and tables are removed from Translation. Source images and task pairings are unchanged.

Each square image uses Generation's shared `gen-reel-image` surface (16 px radius, neutral border, dark background and subtle shadow) and `gen-reel-caption` hierarchy. Three equal cards are capped at 330 px, with 24 px gaps; narrow screens keep three columns with 12 px gaps. No perspective or adjacent previews are introduced. The three MRI input sequences share one full-size source card; T1, T2 and FLAIR buttons select which original image is visible, without overlapping images.

The existing carousel handles previous/next navigation. Generation is unchanged.

Each slide has one centered, neutral-colored modality description above its cards. The duplicate task tab row is removed. Previous/next controls and four clickable indicators reuse Generation’s `gen-reel-controls`, `gen-reel-arrow` and `gen-reel-dots` styles in one centered pill below the three cards; switching updates the visible description and comparison together.

Automatic cycling starts by default every five seconds, wraps back to the first example and continues after manual navigation with a fresh interval. There is no visible Auto-loop toggle. Offscreen, hidden-page and reduced-motion states pause cycling.
