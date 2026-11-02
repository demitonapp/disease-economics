# How SM070 P2 was run (2 November 2026)

P2 filled the AU and NZ grid: for each of the registers' 25 causes, in Australia and in New Zealand at national
level, a figure or a recorded `none` (eight considered sources). `python scripts/grid.py` prints the 50 cells.

1. `python docs/sm070-p2/make_briefs.py <out dir>` writes ten briefs, one per disease per country, from the
   registers' cause text (`vendor/registers-research/diseases.json`) and a list of leads. Each research agent got
   one brief, its own git worktree and branch, and opened one PR.
2. `review-brief.md` is the second pass: a separate agent per PR re-opens every cited source and corrects or
   removes what does not stand. It removed or re-filed figures on four of the ten PRs.
3. `gapfill-common.md` is the third pass for cells a reviewer reopened (`gapfill-example-overrun-au.md` is one
   per-cell assignment).

Rulings the reviews made, which any further research here must keep to:

- A cost-composition share (diesel, materials, labour, services as a share of a cost base) is not evidence of
  plant and fuel, input prices or labour productivity. It is a `context/` figure.
- An owner-side figure is not a contractor figure; a statutory infringement tariff is not a measured cost; a
  frequency or count has no unit in the schema and goes in the `sample_note` of the cell's `none` record.
- A source's `jurisdictions` decide which cell a figure fills: a state-only, GLOBAL or other-country figure does
  not fill a national cell.
