# Visual Turing test

The centered entry presents one 330 px CT preview, a concise invitation, a ten-case description and two choices: Start the test or View expert performance. It uses the existing kidney-tumor CT and mask from `data/turing.json`, rendered through the original `CaseView`; the image is not generated, edited or substituted. No truth label or benchmark chart appears on the initial preview. Choosing View expert performance opens the three original doctor accuracy bars without starting a quiz or showing a user score; visitors can start the test from there or return to preview.

The quiz remains manual: ten randomly selected original cases, existing slice/window geometry, tumor masks, keyboard shortcuts, minimum viewing time and scoring. A 330 px viewer, matching the intro preview, sits above two equal Real/Synthetic buttons. The slice control remains visible; plane/window/zoom/outline controls sit in View options and retain the original viewer event handlers. Back to preview destroys the active viewer and clears the active round.

The completion screen leads with the total number correct out of ten, a Try again button and a Back to preview link. A compact aggregate accuracy chart follows, using the current score and the original junior/all/senior reader-study values from `data/turing.json`. Values remain visible and the chance marker is at 50%. All per-case verdicts/thumbnails are omitted. Answer screenshots are no longer captured. No answers are transmitted or persisted. The other three demo galleries retain automatic cycling.

Verified: preview load; no pre-test statistics; start; slice adjustment; coronal/axial switching; all ten answers and total-score result; restart; exit/reset; 390 px entry and quiz without horizontal overflow; 48 px answer buttons. Styles are scoped to the Turing section in `assets/css/turing.css`.

Preview and quiz share `--turing-image-width` (330 px desktop, 290 px phone), preventing a size jump on Start. The intro reserves a square frame while its volume loads; active planes keep their original physical aspect ratio.

Expert rows appear as Junior, Senior, then All radiologists. The aggregate is separated as a summary row, rather than placed between seniority groups. Both expert-only and completed-test views share this ordering.
