# Report screenshots

Every report image on the page (`public/assets/review-*`, `improve-*`, `define-*`)
is captured from the real report UI with the sample data in `sample-data/`.

1. Copy the built report UI twice, next to these scripts, with the data:

   ```sh
   for v in review improve; do
     cp -R ../../../cli/honest_agent/report_ui $v   # the repo's built report UI
     mkdir -p $v/data && cp sample-data/report-$v.json $v/data/report.json
   done
   ```

2. Serve them: `review/` on port 8766 and `improve/` on port 8767
   (`python3 -m http.server 8766` in each folder).
3. `python shots.py` (needs Playwright and Pillow) writes the images and
   `out/meta.json`. `python shots.py improve-only 1240` or `define-only` redo
   one part.
4. `python place.py` rewrites the hover hotspots and the "Prove it" overlays in
   `Review.astro` and `Improve.astro` from `out/meta.json`. Its regexes match the
   current markup, so adjust them if the sections change.
5. Copy `out/*.webp` and `out/define-*.png` to `public/assets/`.

`add_costs.py` added the v0.4.0 fields (costs, the grading call, step costs) to the
sample data; the data here already has them.

`rename.py` is the one-off rename that turned the 1997/1995 evals into
`revenue_q4` ("Revenue in Q4 2026") and `order_total_2026`. The sample data here
has already been renamed (the data before it is in git history).
SQL in the data stays lowercase, per the repo's `CLAUDE.md`.
