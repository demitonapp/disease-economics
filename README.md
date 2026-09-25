# disease-economics

What published research says the five diseases of a construction job cost, and **where every figure
came from**: the source, the page or table it was read on, whether we read the source itself or
someone's account of it, and any arithmetic we did on the way.

It is maintained by [Demiton](https://demiton.io), whose product uses these figures. That is a
commercial interest, stated in [GOVERNANCE.md](GOVERNANCE.md). The point of publishing the record is
that you don't have to take our word for any of it: every figure can be traced, disputed and changed
under the rules in [METHOD.md](METHOD.md).

**Browse the record at [research.demiton.io](https://research.demiton.io)**, rebuilt on every merge: this repository publishes `corpus.json` to the [`data-latest`](../../releases/tag/data-latest) release, and the site is built from it.

**The figures are estimates with stated confidence, not measurements.** Most of them measure how much
is at stake, not how much a contractor ends up losing. Each one says which.

## The five diseases

| Directory | Disease | Also called (in the Demiton app) |
|---|---|---|
| [`diseases/rework_signal`](diseases/rework_signal) | Rework | Rework |
| [`diseases/overrun_signal`](diseases/overrun_signal) | Cost drift | Baseline overrun |
| [`diseases/claim_window`](diseases/claim_window) | Missed claims (including weather) | Forfeited entitlements |
| [`diseases/evidence_gap`](diseases/evidence_gap) | Disputes | Disputes |
| [`diseases/compliance_gate`](diseases/compliance_gate) | Lapsed compliance | Non-compliance |

The long read that works these figures through a $5 million job is at
[docs.demiton.io/start-here/disease-priority](https://docs.demiton.io/start-here/disease-priority).

## What is here

- **[`sources/`](sources)** - where we got it. One file per paper, report or data release.
- **[`diseases/`](diseases)** - the figures, one file each, in a directory per disease. Exactly one
  figure per disease is the headline.
- **[`context/`](context)** - figures that frame a disease rather than measure it, like a typical
  planned margin. Never a headline.
- **[`protections/`](protections)** - evidence that a protection mechanism matters. No percentages
  saved: nobody has measured that yet.
- **[`schema/`](schema)** and **[`vocab/`](vocab)** - the shape every file must have, and the code
  lists (ISO 3166 jurisdictions, ISIC industries).

## What this is not

- **Not the product.** No product code lives here.
- **Not a model.** It records figures and where they came from. How a product applies them is
  described in [METHOD.md](METHOD.md) and implemented elsewhere.
- **Not a blog.** Prose lives on docs.demiton.io.
- **Not open to unreviewed merging.** Anyone may open a pull request; every one is reviewed.

## Add evidence, or dispute a figure

You don't need to ask anyone. [CONTRIBUTING.md](CONTRIBUTING.md) shows the shape of a pull request,
and CI tells you exactly what is missing. To dispute a figure without writing a file, open a
[dispute issue](../../issues/new?template=dispute.yml) and cite your source.

A disputed figure **stays published**, flagged as disputed, until the dispute is decided. If a
well-argued dispute removed a number, disputing would be the cheapest way to censor the record.

## Licence

- **Data** - the frontmatter and our own words in `sources/`, and everything in `diseases/`,
  `context/`, `protections/` and `vocab/`, and the ledger built from them: [CC BY 4.0](LICENSE).
  Credit it as "disease-economics by Demiton".
- **Code** - `schema/`, `scripts/`, `tests/` and `.github/`: [MIT](LICENSE-CODE).
- **Quoted passages** from sources remain the property of their authors and publishers. They are
  reproduced under fair dealing for research, criticism or review (Copyright Act 1968 (Cth),
  ss 40-41) and are not covered by either licence.

To cite the corpus, see [CITATION.cff](CITATION.cff).
