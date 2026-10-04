// Site settings. This is the only file to edit when links become available.
// Empty links render as disabled "soon" buttons.
window.RADWORLD_SITE = {
  // 'preprint' before acceptance, 'published' after. Switches the paper link and the BibTeX entry.
  status: 'preprint',

  arxivId: '',            // e.g. '2610.01234'. Fills the arXiv link and the BibTeX entry.

  links: {
    paper: '',            // journal article URL, used when status is 'published'
    arxiv: '',            // leave empty to derive it from arxivId
    code: '',             // GitHub repository
    weights: '',          // Hugging Face model page
  },

  // Used for the BibTeX entry when status is 'published'.
  journal: { name: '', volume: '', pages: '', year: '2026', doi: '' },
};
