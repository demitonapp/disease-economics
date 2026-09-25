# Contributing

The most useful thing you can add is a source: a paper, report, data release or judgment that
supports, weakens or replaces a figure here. You don't need to ask first.

## The shape of a pull request

**One source per pull request**, so each can be accepted or rejected on its own.

1. **Add `sources/<slug>.md`.** The slug is `<first-author-or-body>-<year>-<topic>`, lower case with
   hyphens. Copy an existing source file for the frontmatter; [`schema/source.schema.json`](schema/source.schema.json)
   is the full list of fields. The body says what the source says, in your own words.
2. **Cite it from a finding**, in one of three ways:
   - it supports a figure: add its slug to that finding's `sources`;
   - it changes a figure: change the figure, add a `history` entry recording the old one and why,
     and cite the source;
   - it is evidence against a figure that you think should stand anyway, or that we should weigh:
     add it to `considered` with the reason.

   Or add a new finding: `diseases/<disease_key>/<metric_key>.yaml`, the filename in lower case with
   underscores.
3. **Run the checks**, or let CI run them:

   ```
   pip install -r requirements.txt
   python scripts/validate.py --base origin/main
   python -m unittest discover -s tests
   ```

CI says exactly what is missing. A pull request that changes a figure without adding or changing a
source is rejected mechanically; a typo or wording fix needs no source.

## A worked example

A new survey finds rework at 8% of contract value on Australian road projects.

```markdown
<!-- sources/smith-2027-road-rework.md -->
---
title: "Rework on Australian road projects"
organisation: "Smith & Jones"
year: 2027
published_in: "Journal of Construction Engineering and Management 153(2)"
url: "https://doi.org/10.1061/example"
source_type: peer-reviewed
method: records
access: primary
read_on: 2027-03-01
location: "Table 4"
jurisdictions: [AU]
industries: [F42]
---

Cost records from 40 road projects across three contractors. Mean rework was 8% of contract value.
```

Then either a new finding in `diseases/rework_signal/`, or the source added to an existing finding.

## What gets rejected, and why

- **A figure with no source.** The corpus is a record of evidence, not of opinion.
- **A figure you did not read.** If you read it through someone else's citation, say so:
  `access: secondary` and `read_via`. That is allowed; hiding it is not.
- **Arithmetic without the working.** If you calculated a figure, set `derivation: calculated` and
  show the `calculation`.
- **Long quotes.** Quoted passages stay their authors'. Quote a sentence where the exact wording
  matters, no more.
- **Marketing language.** `sample_note` and `caveat` describe the evidence, not what it means for a
  buyer.

## Disputing a figure

Open a [dispute issue](../../issues/new?template=dispute.yml), or a pull request. If the dispute cites a
source, a maintainer marks the figure `disputed` and links your issue; the figure stays published
until the dispute is decided. [GOVERNANCE.md](GOVERNANCE.md) says who decides and how fast.

## Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
