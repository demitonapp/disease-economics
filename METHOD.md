# Method

How a source becomes a figure, and the rules every figure is held to. CI enforces every rule here
that a machine can check ([`scripts/validate.py`](scripts/validate.py)).

## 1. Sources and findings

A **source** (`sources/<slug>.md`) records where something came from and how we read it. Its
frontmatter says:

- `access: primary` - we read the source itself (or its abstract, or its own tables); or
  `access: secondary` - we read someone's account of it, and `read_via` says what.
- `location` - the page, table or paragraph. A finding that uses a different part of the same source
  says so in its citation (`{source: ..., location: ...}`).
- `jurisdictions` and `industries` - what the source covers (Section 6).

A **finding** (`diseases/<disease_key>/<metric_key>.yaml`) is one figure taken from one or more
sources. Its path is its id. The first entry in `sources` is the source of record; the rest
corroborate. Sources reviewed and not used go in `considered`, with the reason, so the record shows
the evidence against a figure as well as for it.

## 2. What kind of money a figure is

Every finding has an `exposure_kind`:

| Kind | Means | Comparable (Section 5) |
|---|---|---|
| `contractor_loss` | Money the contractor actually loses | Yes |
| `money_at_stake` | Money on the table: claimable, held, or in dispute, not necessarily lost | Yes |
| `owner_side` | Money the client mostly pays, such as overruns measured from the decision to build | No |
| `societal` | Costs borne by workers and the community | No |
| `context` | Not a cost: a figure that frames one, like a planned margin (`context/` only) | No |

Kinds are never summed across each other. An exposure built from owner-side money would be the
client's cost counted as the contractor's.

## 3. Units, and when a figure may be multiplied

| Unit | Means | Multiplied by a contract value? |
|---|---|---|
| `ratio_of_contract` | A share of contract value | **Yes, and only this unit** |
| `ratio_of_other` | A share of something else; `denominator` says what | No |
| `per_wet_day`, `per_incident` | An amount per unit; `currency` and `price_year` say which money | No |
| `none` | No defensible figure exists; `exposure_value` is null | No |

The exposure a product may show for a project is `exposure_value x the project's contract value`,
for `ratio_of_contract` only. Every other unit is shown as it is and never multiplied: a cost per
lost day multiplied by a contract value is a large, precise, meaningless number.

A ratio of contract above 1 is a warning, not an error: a share cannot exceed 1, but an overrun from
contract award can.

**Known limit.** `weather_wet_day_overhead` was worked on a $5M contract, so its per-day figure
scales with contract size, which the unit cannot express. Its caveat says so.

## 4. Confidence

| Grade | When |
|---|---|
| **low** | Read second-hand, unverifiable, or a model or estimate rather than an observation |
| **moderate** | Read at source, but any of: one organisation's data; people's own estimates (a perception survey); or a problem the caveat names with how the sample was drawn or how the figure came out of it (a selected caseload, one observation dominating, a re-cut of another source's data) |
| **high** | Read at source, and none of the above |

Our own arithmetic does not change the grade: `derivation: calculated` and `calculation` show it, so
anyone can check it. Where a number is needed, the grades map to 1.0, 0.7 and 0.4.

Under this rule no share-of-contract figure is graded high. That matches the research: confidence in any
single number for these diseases is low, and most studies measure what is at stake rather than what
is lost.

## 5. Which figure applies

There is no headline. No single figure stands for a disease: which one applies depends on where the
work is, and a figure from one country put in front of a contractor in another is the misreading this
record exists to prevent. (Until schema 2.0.0 each disease declared one `is_headline` figure; it was
removed because one global figure never fits a reader filtering by their own state, and one declared
per jurisdiction would be an editorial call per cell with most cells empty.)

A figure is **comparable** when it is a `ratio_of_contract` with a value and its kind is
`contractor_loss` or `money_at_stake`. Only comparable figures are set side by side or multiplied by
a contract value.

When one figure is needed for a place (the Demiton product multiplies one per disease by each
project's contract value), it is the **nearest evidence**, chosen from the comparable figures by
these rules, in order:

1. **Place.** A figure for the place itself (`AU-QLD` for a Queensland project) beats one for its
   country (`AU`), which beats `GLOBAL` (no limit claimed). A figure for another country or another
   state never applies, and neither does `unknown`: no figure is better than someone else's.
2. **Confidence.** high, then moderate, then low.
3. **Kind.** `contractor_loss` before `money_at_stake`: money lost before money at stake.
4. **Recency.** The newer source of record.
5. **Size.** The smaller figure, so a tie never overstates.

The place is the project's location where it is known, and the organisation's country where it is
not. Industry is not part of the rule yet.

## 6. Jurisdictions and industries

- **Jurisdictions:** ISO 3166-1 alpha-2, optionally a 3166-2 subdivision, as a list. `GLOBAL` means
  no jurisdictional limit is claimed; `unknown` means we could not tell. Each stands alone. The UK is
  `GB`. No invented groupings (`ANZ`, `APAC`, `EU`). `AU` means Australia-wide: a national sample, or
  federal law.
- **Industries:** ISIC Rev.4 at division level, written with the section letter (`F42` civil
  engineering, `F41` buildings, `F43` specialised trades, `F` construction unspecified). `ALL` means
  not industry-specific. A source in another taxonomy keeps its own code in `industry_as_published`,
  such as `ANZSIC 31`, and records the ISIC equivalent in `industries`.

A finding's jurisdictions and industries are the union of its sources'.

## 7. Ranges

Optional, and only a range the source reports or our calculation produces. `exposure_range.kind`
says which: `confidence_interval`, `reported_min_max`, `scenario` or `across_studies`. How a range
should propagate into an exposure is not modelled yet.

## 8. Changing a figure

A figure is never overwritten silently. When `exposure_value`, `exposure_unit`, `denominator`,
`exposure_range`, `exposure_kind` or `confidence` changes:

- a `history` entry records the old figure, the date and the reason (append-only), and
- the same pull request adds or changes a file under `sources/`.

A finding is never deleted. It is `withdrawn`, with a `withdrawn_reason`.

## 9. What is deliberately not modelled

- Causation: that a disease caused a loss on a given job.
- Effect sizes for named products, and any leaderboard.
- A single-number verdict per project.
- What a protection saves. The mechanism model is not built; `protections/` holds evidence that a
  mechanism matters, and a figure for what it saves will be a finding here, with sources, when one
  can be defended.

## 10. Schema versions

Every schema in [`schema/`](schema) carries its own semantic version in `x-schema-version`, and the
ledger (`findings.json`) records the versions its rows were validated against. The version is the
schema's, not the data's: releases (`v4`) tag the corpus; schema versions change only when a schema
does. CI refuses a schema change whose version bump is too small:

| Bump | When |
|---|---|
| MAJOR | a property removed, a new requirement, an enum narrowed, a type changed: existing files may stop validating |
| MINOR | a property added, an enum widened: every existing file still validates |
| PATCH | anything else, such as a description or a pattern's wording |

It is the same rule the Demiton product applies to its own data contracts.
