"""Build research.demiton.io from the corpus: an index, a page per disease, a page per figure,
plus the ledger files, sitemap.xml, robots.txt and llms.txt.

    python scripts/build_site.py --out site --release v4

Everything on every page comes from the same files the ledger is built from, so the site cannot
say anything the record does not. The pages work without JavaScript; the script only filters,
copies links, prints, and (after consent) reports usage to GA4.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ledger import rows as ledger_rows, write  # noqa: E402
from validate import ROOT, load_corpus, validate  # noqa: E402

REPO = "https://github.com/demitonapp/disease-economics"
SITE = "https://research.demiton.io"
#: Published on demiton.io and docs.demiton.io; the no-GitHub route for evidence and disputes.
CONTACT = "support@demiton.io"
#: The docs.demiton.io GA4 property: research is read like the docs, and the linker joins the journeys.
GA_ID = "G-L265FEJZF2"
LINKER = ["demiton.io", "app.demiton.io", "docs.demiton.io", "research.demiton.io"]
NAMES_J = json.loads((ROOT / "vocab" / "jurisdictions.json").read_text())
NAMES_I = json.loads((ROOT / "vocab" / "industries.json").read_text())
SHORT_J = {"GB": "UK", "US": "US", "GLOBAL": "Global", "unknown": "Place unknown"}

#: Research-cost order (the order the docs long read argues for), with the public names, the URL
#: slug, a one-line description, and the question a buyer types.
DISEASES = [
    ("rework_signal", "Rework", "rework",
     "Work done twice: poured to the wrong level, built off the wrong drawing, redone after a failed test.",
     "How much does rework cost a construction contractor?"),
    ("overrun_signal", "Cost drift", "cost-drift",
     "The job costing more than it was priced at, and how much of that the contractor carries.",
     "How much do construction projects overrun, and how much does the contractor bear?"),
    ("claim_window", "Missed claims", "missed-claims",
     "Variations, extensions of time, delay costs and retention the contract allowed and nobody claimed in time. Includes weather.",
     "How much money do contractors leave unclaimed in variations, extensions of time and delay costs?"),
    ("evidence_gap", "Disputes", "disputes",
     "Money fought over, what it costs to fight, and how much is recovered.",
     "How much do construction payment disputes cost, and how much is recovered in adjudication?"),
    ("compliance_gate", "Lapsed compliance", "lapsed-compliance",
     "Accidents, lapsed licences and insurance, and the cost of breaching the obligations that come with the job.",
     "What do accidents and lapsed compliance cost a construction contractor?"),
]
SLUG = {k: s for k, _, s, _, _ in DISEASES} | {"context": "context"}
NAME = {k: n for k, n, _, _, _ in DISEASES} | {"context": "Context"}

KIND = {
    "contractor_loss": ("Contractor loss", "Money the contractor actually loses."),
    "money_at_stake": ("Money at stake", "Claimable, held or in dispute: not necessarily lost."),
    "owner_side": ("Owner's money", "Mostly paid by the client. Never counted as the contractor's."),
    "societal": ("Societal", "Borne by workers and the community. Never counted as the contractor's."),
    "context": ("Context", "Not a cost: a figure that frames one."),
}
DENOMINATOR = {
    "budget_at_decision": "of the budget at the decision to build",
    "budget_at_announcement": "of the first promised cost",
    "construction_cost": "of construction cost",
    "amount_claimed": "of the amount claimed",
    "arbitration_cost": "of total arbitration costs",
    "total_injury_cost": "of the total cost of work injury",
    "overrun_additional_cost": "of the extra cost of overruns",
    "annual_capital_budget": "of the year's capital budget",
}
CURRENCY = {"AUD": "A$", "USD": "US$", "NZD": "NZ$", "GBP": "£", "EUR": "€"}
PER = {"per_wet_day": "per wet day", "per_incident": "per case"}
CONFIDENCE_ORDER = {"high": 0, "moderate": 1, "low": 2}
CONFIDENCE_RULE = {
    "high": "read at source, and free of the known weaknesses",
    "moderate": "read at source, but one organisation's data, people's own estimates, or a named sampling problem",
    "low": "read second-hand, unverifiable, or a model or estimate",
}


# ---- formatting -------------------------------------------------------------------------------

def e(s) -> str:
    return escape(str(s)) if s is not None else ""


def pct(v: float) -> str:
    return f"{v * 100:.3g}%"


def money(v: float, currency: str) -> str:
    sym = CURRENCY.get(currency, currency + " ")
    if v >= 1_000_000:
        return f"{sym}{v / 1_000_000:.3g}m"
    return f"{sym}{v:,.0f}"


def figure(f: dict) -> tuple[str, str]:
    """(the number, what it is of) as a reader should see them."""
    unit, v = f["exposure_unit"], f["exposure_value"]
    if unit == "none" or v is None:
        return "No figure", "nobody has published a defensible one"
    if unit == "ratio_of_contract":
        return pct(v), "of contract value"
    if unit == "ratio_of_other":
        return pct(v), DENOMINATOR.get(f.get("denominator") or "", "of " + (f.get("denominator") or "another total"))
    if unit in PER:
        return money(v, f.get("currency") or ""), PER[unit] + (f" ({f['price_year']} {f['currency']})" if f.get("price_year") else "")
    return str(v), unit


def place(js: list[str]) -> str:
    """A short 'where is this from' label: QLD, Australia, NSW, QLD, VIC, Global, US, Canada."""
    if all(j == "AU" or j.startswith("AU-") for j in js):
        subs = [j[3:] for j in js if j.startswith("AU-")]
        return ", ".join(subs) if subs and "AU" not in js else "Australia"
    return ", ".join(SHORT_J.get(j, NAMES_J.get(j, j)) for j in js)


def place_rank(js: list[str]) -> int:
    """Queensland first, then the rest of Australia, New Zealand, global, elsewhere, unknown."""
    if "AU-QLD" in js:
        return 0
    if any(j == "AU" or j.startswith("AU-") for j in js):
        return 1
    if "NZ" in js:
        return 2
    if "GLOBAL" in js:
        return 3
    return 5 if js == ["unknown"] else 4


def order(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (
        not r["is_headline"], r.get("status") == "withdrawn", place_rank(r["jurisdictions"]),
        CONFIDENCE_ORDER.get(r["confidence"], 9), r["id"]))


def page_url(row: dict) -> str:
    return f"/{SLUG[row['disease_key'] or 'context']}/{row['metric_key']}/"


def source_of_record(row: dict, sources: dict) -> dict:
    return sources[row["_citations"][0]["source"]]


def attribution(row: dict, sources: dict) -> str:
    """Who and when: 'QBCC, 2021 to 2025' for a series, 'Love et al., 2017, and 2 others' for a mix."""
    cited = [sources[c["source"]] for c in row["_citations"]]
    orgs = {s["organisation"] for s in cited}
    years = sorted({s["year"] for s in cited})
    if len(orgs) == 1:
        span = str(years[0]) if len(years) == 1 else f"{years[0]} to {years[-1]}"
        return f"{cited[0]['organisation']}, {span}"
    more = len(cited) - 1
    return f"{cited[0]['organisation']}, {cited[0]['year']}, and {more} other source{'s' if more > 1 else ''}"


def short_title(text: str, limit: int = 58) -> str:
    """Cut at a word boundary so a search result shows a whole phrase."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:(") + "..."


def sentence(row: dict, sources: dict) -> str:
    """One quotable sentence for a figure: the number, what it is of, where from, who, how sure."""
    num, of = figure(row)
    return (f"{num} {of}: {row['label']} ({attribution(row, sources)}; "
            f"{place(row['jurisdictions'])}; {row['confidence']} confidence).")


def ld(obj) -> str:
    return '<script type="application/ld+json">' + json.dumps(obj).replace("</", "<\\/") + "</script>"


# ---- data ---------------------------------------------------------------------------------------

def load() -> dict:
    _, sources, findings, _ = load_corpus(ROOT)
    data = ledger_rows(ROOT)
    paths = {}
    for path, f in findings.items():
        parts = Path(path).parts
        rid = f"context/{Path(path).stem}" if parts[0] == "context" else f"{parts[1]}/{Path(path).stem}"
        paths[rid] = (path, f)
    for r in data:
        path, f = paths[r["id"]]
        r["_path"] = path
        r["_citations"] = [c if isinstance(c, dict) else {"source": c} for c in f["sources"]]
    current = [r for r in data if r.get("status") != "withdrawn"]
    cited_now = {c["source"] for r in current for c in r["_citations"]}
    schemas = {p.name: json.loads(p.read_text()).get("x-schema-version", "")
               for p in sorted((ROOT / "schema").glob("*.schema.json"))}
    return {
        "sources": sources, "data": data, "current": current,
        "n_second": sum(1 for slug in cited_now if sources[slug]["access"] == "secondary"),
        "by_d": {k: order([r for r in data if r["disease_key"] == k]) for k, *_ in DISEASES},
        "context": order([r for r in data if r["family"] == "context"]),
        "schema_version": schemas.get("finding.schema.json", ""),
    }


# ---- components ------------------------------------------------------------------------------

def source_line(slug: str, src: dict, location: str | None) -> str:
    sec = ' <span class="tag warn">second-hand</span>' if src["access"] == "secondary" else ""
    link = f'<a href="{e(src["url"])}" rel="noopener">{e(src["title"])}</a>' if src.get("url") else e(src["title"])
    free = f' · <a href="{e(src["free_copy_url"])}" rel="noopener">free copy</a>' if src.get("free_copy_url") else ""
    via = f'<div class="via">Read via: {e(src["read_via"])}</div>' if src["access"] == "secondary" and src.get("read_via") else ""
    return (
        f'<li><span class="org">{e(src["organisation"])} ({e(src["year"])})</span>, {link}{free}{sec}'
        f'<div class="loc">{e(location or src["location"])} · <a href="{REPO}/blob/main/sources/{e(slug)}.md">source record</a></div>{via}</li>'
    )


def flags(row: dict) -> str:
    kind_label, kind_help = KIND.get(row["exposure_kind"], (row["exposure_kind"], ""))
    status = row.get("status") or "current"
    out = [f'<span class="tag place" title="Where the evidence is from">{e(place(row["jurisdictions"]))}</span>']
    if row["is_headline"]:
        out.append('<span class="tag headline">Headline</span>')
    out.append(f'<span class="tag conf-{e(row["confidence"])}" title="METHOD.md Section 4">{e(row["confidence"]).capitalize()} confidence</span>')
    out.append(f'<span class="tag kind" title="{e(kind_help)}">{e(kind_label)}</span>')
    if row.get("source_secondary"):
        out.append('<span class="tag warn">Second-hand</span>')
    if status == "disputed":
        out.append(f'<a class="tag bad" href="{e(row.get("dispute_url"))}">Disputed</a>')
    if status == "withdrawn":
        out.append('<span class="tag bad">Withdrawn</span>')
    return "".join(out)


def finding_body(row: dict, sources: dict) -> str:
    num, _ = figure(row)
    status = row.get("status") or "current"
    cites = "".join(source_line(c["source"], sources[c["source"]], c.get("location")) for c in row["_citations"])
    considered = "".join(
        f'<li><span class="org">{e(sources[c["source"]]["organisation"])}</span>: {e(c["reason"])}</li>'
        for c in row.get("considered") or [])
    history = "".join(
        f'<li><span class="mono">{e(h["changed_on"])}</span> {e(h["reason"])}</li>' for h in row.get("history") or [])
    rng = row.get("exposure_range")
    rng_html = ""
    if rng:
        lo, hi = (pct(rng["low"]), pct(rng["high"])) if "ratio" in row["exposure_unit"] else (
            money(rng["low"], row.get("currency") or ""), money(rng["high"], row.get("currency") or ""))
        rng_html = f'<p class="range">Range {e(lo)} to {e(hi)} ({e(rng["kind"].replace("_", " "))})</p>'
    calc = f'<p><strong>Our arithmetic.</strong> {e(row["calculation"])}</p>' if row.get("calculation") else ""
    withdrawn = f'<p class="bad-text"><strong>Withdrawn.</strong> {e(row["withdrawn_reason"])}</p>' if status == "withdrawn" else ""
    basis = row["exposure_basis"]
    basis = f"{num} {basis}" if basis.startswith("of ") and row["exposure_value"] is not None else basis[:1].upper() + basis[1:]
    where = ", ".join(row["jurisdictions"]) + " · " + ", ".join(row["industries"])
    url = SITE + page_url(row)
    return f"""
    {withdrawn}
    <p><strong>What it is.</strong> {e(basis)}.</p>
    {rng_html}
    <p><strong>Sample.</strong> {e(row['sample_note'])}</p>
    <p><strong>What it is not.</strong> {e(row['caveat'])}</p>
    {calc}
    <h3>Where it came from</h3>
    <ul class="cites">{cites}</ul>
    {f'<h3>Considered and set aside</h3><ul class="cites">{considered}</ul>' if considered else ''}
    {f'<h3>History</h3><ul class="hist">{history}</ul>' if history else ''}
    <p class="meta"><span class="mono">{e(row['id'])}</span> · {e(where)} ·
      <a href="{REPO}/blob/main/{e(row['_path'])}">the record</a> ·
      <a class="copy-link" href="{e(url)}" data-finding="{e(row['id'])}">link to this figure</a> ·
      <a class="dispute-link" data-finding="{e(row['id'])}" href="{REPO}/issues/new?template=dispute.yml&amp;finding={e(row['_path'])}">dispute this figure</a>
      <span class="muted">(or email {CONTACT})</span></p>"""


def finding_card(row: dict, sources: dict) -> str:
    num, of = figure(row)
    status = row.get("status") or "current"
    return f"""
<details class="finding{' is-headline' if row['is_headline'] else ''}{' is-withdrawn' if status == 'withdrawn' else ''}" id="{e(row['id'])}" data-j="{e(' '.join(row['jurisdictions']))}" data-i="{e(' '.join(row['industries']))}">
  <summary>
    <span class="fig"><span class="num">{e(num)}</span><span class="of">{e(of)}</span></span>
    <span class="what"><span class="label">{e(row['label'])}</span><span class="flags">{flags(row)}</span></span>
    <span class="chev" aria-hidden="true"></span>
  </summary>
  <div class="body">{finding_body(row, sources)}
    <p class="open-page"><a href="{page_url(row)}">Open this figure's own page</a></p>
  </div>
</details>"""


def answer(key: str, ctx: dict) -> str:
    """The answer-first paragraph for a disease, written from the data, so it cannot drift from it."""
    rows = [r for r in ctx["by_d"][key] if r.get("status") != "withdrawn"]
    head = next((r for r in rows if r["is_headline"]), None)
    srcs = {c["source"] for r in rows for c in r["_citations"]}
    qld = [r for r in rows if "AU-QLD" in r["jurisdictions"]]
    parts = []
    if head:
        num, of = figure(head)
        parts.append(f"Published research puts it at {num} {of}: {head['label']} ({attribution(head, ctx['sources'])}; "
                     f"{head['confidence']} confidence).")
    parts.append(f"The record holds {len(rows)} figures on {NAME[key].lower()} from {len(srcs)} sources.")
    if qld:
        q = qld[0]
        num, of = figure(q)
        parts.append(f"Queensland: {len(qld)} figure{'s' if len(qld) > 1 else ''}, including {num} {of} ({q['label']}).")
    else:
        parts.append("No Queensland-specific figure yet; the Australian figures apply.")
    return " ".join(parts)


def qa(key: str, ctx: dict) -> list[tuple[str, str]]:
    """Buyer questions for a disease, each answered from the record."""
    rows = [r for r in ctx["by_d"][key] if r.get("status") != "withdrawn"]
    head = next((r for r in rows if r["is_headline"]), None)
    question = next(q for k, *_, q in DISEASES if k == key)
    others = [r for r in rows if r is not head and r["exposure_value"] is not None][:4]
    a1 = (sentence(head, ctx["sources"]) + " " if head else "") + (
        "Other figures in the record: " + "; ".join(f"{figure(r)[0]} {figure(r)[1]} ({place(r['jurisdictions'])})" for r in others) + "."
        if others else "")
    qld = [r for r in rows if "AU-QLD" in r["jurisdictions"]]
    a2 = (" ".join(sentence(r, ctx["sources"]) for r in qld[:3]) if qld
          else f"Not yet. The record has no Queensland-specific figure on {NAME[key].lower()}; the Australia-wide figures apply.")
    a3 = (f"The headline is graded {head['confidence']} confidence: {CONFIDENCE_RULE[head['confidence']]}. "
          f"What it is not: {head['caveat']}") if head else "There is no headline figure for this disease yet."
    return [(question, a1.strip()),
            (f"Is there Queensland evidence on {NAME[key].lower()}?", a2),
            (f"How reliable is the {NAME[key].lower()} figure?", a3)]


def table(rows: list[dict], sources: dict) -> str:
    body = "".join(
        f'<tr><td class="mono">{e(figure(r)[0])}</td><td>{e(figure(r)[1])}</td><td><a href="{page_url(r)}">{e(r["label"])}</a></td>'
        f'<td>{e(place(r["jurisdictions"]))}</td><td>{e(r["confidence"])}</td>'
        f'<td>{e(source_of_record(r, sources)["organisation"])} ({e(source_of_record(r, sources)["year"])})</td></tr>'
        for r in rows if r.get("status") != "withdrawn")
    return (f'<div class="tablewrap"><table><thead><tr><th>Figure</th><th>Of</th><th>What it measures</th><th>Where</th>'
            f'<th>Confidence</th><th>Source</th></tr></thead><tbody>{body}</tbody></table></div>')


def filter_bar(data: list[dict]) -> str:
    """Jurisdiction and industry selects, built from the codes the findings actually use."""
    used_j = {j for r in data for j in r["jurisdictions"]}
    used_i = {i for r in data for i in r["industries"]}
    countries = sorted({j.split("-")[0] for j in used_j if j not in ("GLOBAL", "unknown")}, key=lambda c: NAMES_J.get(c, c))
    opts_j = ['<option value="">All jurisdictions</option>']
    for c in countries:
        subs = sorted(j for j in used_j if j.startswith(c + "-"))
        opts_j.append(f'<option value="{e(c)}">{e(NAMES_J.get(c, c) + (" (all)" if subs else ""))}</option>')
        opts_j += [f'<option value="{e(s)}">&nbsp;&nbsp;{e(NAMES_J.get(s, s))}</option>' for s in subs]
    for special, label in (("GLOBAL", "Global (no limit claimed)"), ("unknown", "Unknown")):
        if special in used_j:
            opts_j.append(f'<option value="{special}">{label}</option>')
    opts_i = ['<option value="">All industries</option>']
    if used_i & {"F", "F41", "F42", "F43"}:
        opts_i.append('<option value="F">Construction (any)</option>')
    opts_i += [f'<option value="{c}">&nbsp;&nbsp;{e(NAMES_I[c])}</option>' for c in ("F42", "F41", "F43") if c in used_i]
    for special, label in (("ALL", "Not industry-specific"), ("unknown", "Unknown")):
        if special in used_i:
            opts_i.append(f'<option value="{special}">{label}</option>')
    return f"""<div class="filters" id="f-bar"><div class="wrap">
  <label>Jurisdiction <select id="f-j">{''.join(opts_j)}</select></label>
  <label>Industry <select id="f-i">{''.join(opts_i)}</select></label>
  <span class="broad"><label><input type="checkbox" id="f-broad" checked> Include broader evidence</label><button type="button" class="info" popovertarget="broad-help" aria-label="What counts as broader evidence?">?</button></span>
  <button type="button" id="f-reset" hidden>Clear</button>
  <span class="count" id="f-count" aria-live="polite"></span>
</div></div>
  <div id="broad-help" popover class="pop" role="dialog" aria-labelledby="broad-help-title">
    <h3 id="broad-help-title">What counts as broader evidence</h3>
    <p>Figures that don't name your exact selection but still apply to it.</p>
    <p><strong>Jurisdiction.</strong> Pick a state and you also get Australia-wide figures and global ones (whose source claims no geographic limit). Pick a country and you get all its states plus global figures.</p>
    <p><strong>Industry.</strong> Pick a division, such as civil engineering, and you also get figures for construction in general and figures that aren't industry-specific. Pick Construction (any) and you also get the ones that aren't industry-specific.</p>
    <p><strong>It never adds a sibling.</strong> Queensland never pulls in NSW-only, New Zealand or US figures; civil engineering never pulls in buildings-only figures. A figure covering several states counts for each of them either way.</p>
    <p class="eg" id="broad-eg"></p>
    <p>It's on by default because there's little place-specific evidence yet for most diseases. Turn it off to see only what was measured where you picked.</p>
    <button type="button" class="pop-close" popovertarget="broad-help" popovertargetaction="hide">Close</button>
  </div>"""


# ---- layout -------------------------------------------------------------------------------------

CSS = """
:root {
  --bg: #0B1220; --surface: #111827; --panel: #1F2937; --border: #374151;
  --text: #F9FAFB; --muted: #9CA3AF; --steel: #5B8DB8; --violet: #7C3AED; --violet-text: #A78BFA;
  --green: #059669; --amber: #D97706; --red: #DC2626;
  --serif: "Newsreader", Georgia, serif; --sans: "Inter", system-ui, sans-serif; --mono: "IBM Plex Mono", ui-monospace, monospace;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--bg); color: var(--text); font: 16px/1.6 var(--sans); }
a { color: var(--steel); }
a:hover { color: #7FA7CC; }
a:focus-visible, summary:focus-visible, button:focus-visible { outline: 2px solid var(--violet-text); outline-offset: 2px; }
.wrap { max-width: 960px; margin: 0 auto; padding: 0 16px; }
header.top { border-bottom: 1px solid var(--border); }
header.top .wrap { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-top: 16px; padding-bottom: 16px; }
.wordmark { font: 500 14px var(--sans); letter-spacing: .15em; color: var(--text); text-decoration: none; display: inline-flex; align-items: center; gap: 10px; padding: 4px 0; line-height: 16px; }
.wordmark img { display: block; }
.top-links a { margin-left: 16px; font-size: 14px; display: inline-block; padding: 4px 0; line-height: 16px; }
.hero { padding-top: 56px; padding-bottom: 24px; }
.crumbs { font-size: 14px; color: var(--muted); padding-top: 24px; }
.crumbs a { color: var(--muted); }
h1 { font: 500 clamp(32px, 5.5vw, 52px)/1.12 var(--serif); margin: 0 0 16px; }
h2 { font: 500 clamp(24px, 4vw, 34px)/1.2 var(--serif); margin: 0 0 8px; }
h3.q { font: 600 17px/1.4 var(--sans); margin: 20px 0 6px; }
main > h2 { margin-top: 40px; }
.finding h3 { font: 600 13px var(--sans); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 20px 0 8px; }
.skip { position: absolute; left: 16px; top: -48px; background: var(--violet); color: #fff; padding: 8px 12px; border-radius: 6px; z-index: 10; }
.skip:focus { top: 12px; }
.lede { font-size: 19px; color: #D1D5DB; max-width: 44em; }
.updated { font-size: 14px; color: var(--muted); margin: 8px 0 0; }
.answer { font-size: 17px; color: #E5E7EB; max-width: 46em; margin: 8px 0 16px; }
.nogh { color: var(--muted); font-size: 14px; margin: 12px 0 0; }
.stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 8px; }
.stat { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; min-width: 120px; color: var(--text); text-decoration: none; }
.stat b { display: block; font: 500 24px var(--mono); }
.stat span { font-size: 13px; color: var(--muted); }
a.stat:hover { border-color: var(--steel); }
.cta { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 0; }
.btn { display: inline-block; padding: 10px 16px; border-radius: 6px; border: 1px solid var(--border); color: var(--text); text-decoration: none; font-weight: 500; font-size: 15px; }
.btn.primary { background: var(--violet); border-color: var(--violet); color: #fff; }
.btn.primary:hover { background: #6D28D9; color: #fff; }
.btn:hover { border-color: var(--steel); color: var(--text); }
.method { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-top: 16px; }
.method ul { margin: 8px 0 0; padding-left: 18px; }
nav.diseases { position: sticky; top: 0; z-index: 2; background: rgba(11,18,32,.95); border-bottom: 1px solid var(--border); backdrop-filter: blur(6px); }
nav.diseases .wrap { display: flex; gap: 20px; overflow-x: auto; padding-top: 12px; padding-bottom: 12px; white-space: nowrap; }
nav.diseases a { color: var(--muted); text-decoration: none; font-size: 14px; font-weight: 500; display: inline-block; padding: 4px 0; line-height: 16px; }
nav.diseases a:hover { color: var(--text); }
nav.diseases a.dim { opacity: .45; }
.f-toggle { display: none; margin-left: auto; background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 4px 12px; font: 500 14px var(--sans); min-height: 28px; }
.filters { border-top: 1px solid var(--border); }
html:not(.js) .filters, html:not(.js) .f-toggle { display: none !important; }
.filters .wrap { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; padding-top: 10px; padding-bottom: 10px; font-size: 14px; min-height: 57px; }
.filters label { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); min-height: 24px; }
.filters select { background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font: 14px var(--sans); max-width: 60vw; }
.filters input[type=checkbox] { accent-color: var(--violet); width: 20px; height: 20px; }
.broad { display: inline-flex; align-items: center; gap: 6px; }
.info { width: 24px; height: 24px; border-radius: 50%; border: 1px solid var(--border); background: var(--surface); color: var(--muted); font: 600 13px var(--sans); cursor: pointer; padding: 0; line-height: 22px; }
.info:hover { color: var(--text); border-color: var(--steel); }
.pop { max-width: min(460px, calc(100vw - 32px)); background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 20px 22px 16px; box-shadow: 0 16px 48px rgba(0,0,0,.6); font: 15px/1.55 var(--sans); white-space: normal; max-height: calc(100vh - 32px); overflow-y: auto; }
.pop::backdrop { background: rgba(11,18,32,.55); }
.pop h3 { font: 500 20px/1.3 var(--serif); margin: 0 0 8px; }
.pop p { margin: 0 0 10px; color: #D1D5DB; }
.pop .eg { color: var(--text); font-family: var(--mono); font-size: 13px; }
.pop .eg:empty { display: none; }
.pop-close { margin-top: 4px; background: var(--violet); color: #fff; border: 0; border-radius: 6px; padding: 8px 14px; font: 600 14px var(--sans); cursor: pointer; min-height: 24px; }
.filters .count { margin-left: auto; color: var(--muted); font-family: var(--mono); font-size: 13px; }
.filters button { background: none; border: 0; color: var(--steel); font: 14px var(--sans); cursor: pointer; padding: 4px 8px; min-height: 24px; }
section { padding: 48px 0 8px; scroll-margin-top: 110px; }
section.is-empty { padding-top: 20px; }
section.is-empty h2 { font-size: 20px; color: var(--muted); }
section.is-empty .blurb, section.is-empty .answer, section.is-empty .more, section.is-empty .headline-line { display: none; }
.empty { color: var(--muted); font-style: italic; }
[hidden] { display: none !important; }
.blurb { color: var(--muted); margin: 0 0 8px; max-width: 44em; }
.more { margin: 0 0 16px; font-size: 15px; }
.muted { color: var(--muted); }
.mono { font-family: var(--mono); }
.finding { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin: 10px 0; }
.finding.is-headline { border-color: var(--steel); }
.finding.is-withdrawn { opacity: .6; }
.finding summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: 150px 1fr 14px; gap: 16px; padding: 16px; }
.finding summary::-webkit-details-marker { display: none; }
.chev { width: 10px; height: 10px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(45deg); margin-top: 8px; transition: transform .15s; justify-self: end; }
details[open] > summary .chev { transform: rotate(-135deg); margin-top: 14px; }
.finding summary:hover .chev { border-color: var(--text); }
.fig { display: flex; flex-direction: column; }
.num { font: 500 26px/1.1 var(--mono); }
.of { font-size: 12px; color: var(--muted); margin-top: 4px; }
.label { display: block; font-weight: 500; }
.flags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); text-decoration: none; }
.tag.place { border-color: var(--steel); color: #BFD3E6; }
.tag.headline { border-color: var(--steel); color: var(--text); }
.tag.conf-high { border-color: var(--green); color: #6EE7B7; }
.tag.conf-moderate { border-color: var(--amber); color: #FCD34D; }
.tag.conf-low { border-color: var(--red); color: #FCA5A5; }
.tag.warn { border-color: var(--amber); color: #FCD34D; }
.tag.bad { border-color: var(--red); color: #FCA5A5; }
.bad-text { color: #FCA5A5; }
.finding .body { padding: 0 16px 16px; border-top: 1px solid var(--border); }
.finding .body p, .solo p { margin: 12px 0; max-width: 48em; }
.cites, .hist, .sources { margin: 0; padding-left: 18px; }
.cites li, .sources li { margin: 6px 0; }
.org { font-weight: 500; }
.loc, .via { font-size: 13px; color: var(--muted); }
.meta { font-size: 13px; color: var(--muted); border-top: 1px solid var(--border); padding-top: 12px; }
.range { font-family: var(--mono); font-size: 14px; }
.open-page { font-size: 14px; }
.copy-link.copied::after { content: " (copied)"; color: var(--muted); }
.big { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin: 8px 0 16px; }
.big .num { font-size: 44px; }
.big .of { font-size: 16px; }
.solo { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 4px 20px 16px; }
.solo h3 { font: 600 13px var(--sans); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 20px 0 8px; }
.tablewrap { overflow-x: auto; margin: 16px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 500; }
.faq { max-width: 48em; }
.faq p { margin: 0 0 8px; color: #D1D5DB; }
footer { border-top: 1px solid var(--border); margin-top: 64px; padding: 32px 0 48px; color: var(--muted); font-size: 14px; }
footer button { background: none; border: 0; padding: 0; color: var(--steel); font: inherit; text-decoration: underline; cursor: pointer; }
@media (max-width: 640px) {
  .finding summary { grid-template-columns: auto 1fr 14px; gap: 4px 12px; padding: 12px; align-items: start; }
  .finding summary .what { grid-column: 1 / 3; }
  .finding summary .chev { grid-row: 1; grid-column: 3; }
  .num { font-size: 22px; }
  .big .num { font-size: 36px; }
  .fig { flex-direction: row; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .of { margin-top: 0; }
  .flags { margin-top: 6px; gap: 4px; }
  .top-links a { margin-left: 12px; font-size: 13px; }
  nav.diseases .wrap { gap: 16px; }
  html.js .f-toggle { display: inline-block; }
  .filters { display: none; }
  nav.diseases.show-filters .filters { display: block; }
  .filters .count { margin-left: 0; }
  section { scroll-margin-top: 56px; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .chev { transition: none; }
}
@media print {
  body { background: #fff; color: #000; }
  a { color: #000; }
  nav.diseases, .cta, .nogh, .top-links, .skip, .chev, .filters, #dc-banner { display: none !important; }
  .finding, .stat, .method, .solo { background: #fff; border-color: #999; break-inside: avoid; }
  .lede, .blurb, .of, .loc, .via, .meta, .muted, .stat span, .finding h3, .answer, .faq p { color: #333; }
  .tag { color: #000; border-color: #666; }
}
"""

#: Consent Mode v2, as docs.demiton.io runs it: analytics is off until someone accepts, and the
#: choice can be withdrawn from the footer. Events are sent only if gtag exists and consent allows.
ANALYTICS_JS = """
(function(){
  var G='%(ga)s',K='demiton_consent_v1';
  window.dataLayer=window.dataLayer||[];
  function gtag(){dataLayer.push(arguments);}
  window.gtag=gtag;
  gtag('consent','default',{analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',functionality_storage:'granted',security_storage:'granted',wait_for_update:500});
  var c=null; try{c=localStorage.getItem(K);}catch(e){}
  if(c==='accepted')gtag('consent','update',{analytics_storage:'granted'});
  var s=document.createElement('script');s.async=true;s.src='https://www.googletagmanager.com/gtag/js?id='+G;document.head.appendChild(s);
  gtag('js',new Date());
  gtag('config',G,{send_page_view:true,linker:{domains:%(linker)s,accept_incoming:true}});
  if(!c){document.addEventListener('DOMContentLoaded',function(){
    var b=document.createElement('div');b.id='dc-banner';b.setAttribute('role','region');b.setAttribute('aria-label','Analytics consent');
    b.setAttribute('style','position:fixed;bottom:1rem;right:1rem;z-index:9999;max-width:min(300px,calc(100vw - 2rem));background:#111827;border:1px solid #374151;border-radius:8px;padding:1rem;box-shadow:0 8px 40px rgba(0,0,0,.6);font-family:Inter,system-ui,sans-serif;');
    b.innerHTML='<p style="font-size:13px;color:#D1D5DB;line-height:1.5;margin:0 0 .75rem">We use GA4 analytics to see how this research is used. <a href="https://demiton.io/privacy-policy" style="color:#5B8DB8" rel="noopener">Privacy policy</a>.</p><div style="display:flex;gap:.5rem"><button type="button" id="dc-a" style="flex:1;background:#7C3AED;color:#fff;font:600 13px Inter,sans-serif;padding:.5rem;border:0;border-radius:6px;cursor:pointer">Accept</button><button type="button" id="dc-d" style="flex:1;background:none;color:#D1D5DB;font:13px Inter,sans-serif;padding:.5rem;border:1px solid #374151;border-radius:6px;cursor:pointer">Decline</button></div>';
    document.body.appendChild(b);
    document.getElementById('dc-a').onclick=function(){try{localStorage.setItem(K,'accepted');}catch(e){}gtag('consent','update',{analytics_storage:'granted'});b.remove();};
    document.getElementById('dc-d').onclick=function(){try{localStorage.setItem(K,'declined');}catch(e){}b.remove();};
  });}
  document.addEventListener('click',function(ev){
    var el=ev.target; if(!(el instanceof Element)||!el.closest('[data-cookie-reset]'))return;
    try{localStorage.removeItem(K);}catch(e){}
    gtag('consent','update',{analytics_storage:'denied'}); location.reload();
  });
})();
""" % {"ga": GA_ID, "linker": json.dumps(LINKER)}

#: On every page: deep links open a card, copy-link, print-everything, and usage events.
COMMON_JS = """
(() => {
  const ev = (name, params) => { if (window.gtag) window.gtag('event', name, params || {}); };
  function openFromHash() {
    const id = decodeURIComponent(location.hash.slice(1));
    const d = id && document.getElementById(id);
    if (d && d.tagName === 'DETAILS') {
      if (d.hidden && window.clearFilters) window.clearFilters();
      d.open = true; d.scrollIntoView({ block: 'start' });
    }
  }
  window.addEventListener('hashchange', openFromHash);
  openFromHash();
  document.querySelectorAll('details.finding').forEach((d) => d.addEventListener('toggle', () => {
    if (d.open) ev('finding_open', { finding_id: d.id });
  }));
  document.querySelectorAll('.copy-link').forEach((a) => a.addEventListener('click', (e) => {
    if (!navigator.clipboard) return;
    e.preventDefault();
    navigator.clipboard.writeText(a.href).then(() => { a.classList.add('copied'); setTimeout(() => a.classList.remove('copied'), 1500); }, () => { location.href = a.href; });
    ev('finding_link_copy', { finding_id: a.dataset.finding });
  }));
  document.addEventListener('click', (e) => {
    const a = e.target instanceof Element && e.target.closest('a');
    if (!a) return;
    const h = a.getAttribute('href') || '';
    if (/findings\\.(csv|json)$/.test(h)) ev('data_download', { format: h.split('.').pop() });
    else if (h.includes('template=new-evidence')) ev('suggest_source_click');
    else if (a.classList.contains('dispute-link')) ev('dispute_click', { finding_id: a.dataset.finding });
    else if (h.includes('CONTRIBUTING')) ev('contribute_click');
    else if (h.startsWith('mailto:')) ev('email_click');
  });
  let wasOpen = [];
  window.addEventListener('beforeprint', () => {
    wasOpen = [...document.querySelectorAll('details.finding')].map((d) => d.open);
    document.querySelectorAll('details.finding').forEach((d) => { d.open = true; });
  });
  window.addEventListener('afterprint', () => {
    document.querySelectorAll('details.finding').forEach((d, i) => { d.open = wasOpen[i]; });
  });
})();
"""

#: Index only: jurisdiction and industry filters. Every finding is in the HTML without it.
FILTER_JS = """
(() => {
  const $ = (id) => document.getElementById(id);
  const selJ = $('f-j'), selI = $('f-i'), broad = $('f-broad'), reset = $('f-reset'), count = $('f-count');
  const toggle = $('f-toggle'), nav = document.querySelector('nav.diseases');
  toggle.addEventListener('click', () => {
    const open = nav.classList.toggle('show-filters');
    toggle.setAttribute('aria-expanded', String(open));
  });
  const q = new URLSearchParams(location.search);
  if (q.get('j')) selJ.value = q.get('j');
  if (q.get('i')) selI.value = q.get('i');
  if (q.get('broad') === '0') broad.checked = false;
  const list = (el, k) => (el.dataset[k] || '').split(' ').filter(Boolean);
  const matchJ = (js, v, b) => !v || js.some((j) => j === v || j.startsWith(v + '-'))
    || (b && v !== 'GLOBAL' && v !== 'unknown' && (js.includes('GLOBAL') || (v.includes('-') && js.includes(v.split('-')[0]))));
  const isCon = (i) => i === 'F' || /^F4[123]$/.test(i);
  const matchI = (is, v, b) => !v || (v === 'F' ? is.some(isCon) : is.includes(v))
    || (b && v !== 'ALL' && v !== 'unknown' && (is.includes('ALL') || (v !== 'F' && is.includes('F'))));
  function apply(fromUser) {
    const vj = selJ.value, vi = selI.value, b = broad.checked;
    const keep = (el) => matchJ(list(el, 'j'), vj, b) && matchI(list(el, 'i'), vi, b);
    let shown = 0, total = 0;
    document.querySelectorAll('details.finding').forEach((d) => {
      const ok = keep(d); d.hidden = !ok;
      if (!d.classList.contains('is-withdrawn')) { total++; if (ok) shown++; }
    });
    document.querySelectorAll('main section').forEach((s) => {
      const empty = s.querySelector('.empty');
      if (!empty) return;
      const none = !s.querySelector('details.finding:not([hidden])');
      empty.hidden = !none;
      s.classList.toggle('is-empty', none);
      const link = document.querySelector(`nav.diseases a[href="#${s.id}"]`);
      if (link) link.classList.toggle('dim', none);
    });
    document.querySelectorAll('.headline-line').forEach((h) => {
      const card = document.getElementById(h.dataset.for);
      h.hidden = !!(card && card.hidden);
    });
    document.querySelectorAll('ul.sources li').forEach((li) => { li.hidden = !keep(li); });
    const on = !!(vj || vi);
    count.textContent = on ? `Showing ${shown} of ${total} figures` : `${total} figures`;
    reset.hidden = !on;
    toggle.textContent = on ? `Filter (${[vj, vi].filter(Boolean).length})` : 'Filter';
    const p = new URLSearchParams();
    if (vj) p.set('j', vj); if (vi) p.set('i', vi); if (!b) p.set('broad', '0');
    history.replaceState(null, '', (p.toString() ? '?' + p : location.pathname) + location.hash);
    if (fromUser && window.gtag) window.gtag('event', 'filter_change', { jurisdiction: vj || 'all', industry: vi || 'all', broader: b });
  }
  [selJ, selI, broad].forEach((el) => el.addEventListener('change', () => apply(true)));
  reset.addEventListener('click', () => { selJ.value = ''; selI.value = ''; broad.checked = true; apply(true); });
  window.clearFilters = () => { selJ.value = ''; selI.value = ''; apply(false); };
  const live = [...document.querySelectorAll('details.finding')].filter((d) => !d.classList.contains('is-withdrawn'));
  const qld = (b) => live.filter((d) => matchJ(list(d, 'j'), 'AU-QLD', b)).length;
  const eg = $('broad-eg');
  if (eg) eg.textContent = `For example, Queensland: ${qld(false)} figures with it off, ${qld(true)} with it on.`;
  apply(false);
})();
"""


def layout(*, title: str, description: str, path: str, body: str, today: str, release: str,
           json_ld: list[str], og_title: str | None = None, scripts: str = "", nav: str = "") -> str:
    url = SITE + path
    return f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>document.documentElement.classList.add('js')</script>
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Demiton research">
<meta property="og:url" content="{e(url)}">
<meta property="og:title" content="{e(og_title or title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:image" content="{SITE}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="What the diseases of a construction job cost, and where every figure came from. Demiton research.">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" type="text/csv" href="/findings.csv" title="All findings (CSV)">
<link rel="alternate" type="application/json" href="/findings.json" title="All findings (JSON)">
{''.join(json_ld)}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:opsz,wght@6..72,500&family=IBM+Plex+Mono:wght@400;500&display=optional" rel="stylesheet">
<style>{CSS}</style>
<script>{ANALYTICS_JS}</script>
</head>
<body>
<a class="skip" href="#main">Skip to the figures</a>
<header class="top"><div class="wrap">
  <a class="wordmark" href="/"><img src="/logo.png" alt="" width="24" height="24">DEMITON</a>
  <span class="top-links"><a href="https://docs.demiton.io/start-here/disease-priority">The long read</a><a href="{REPO}">GitHub</a></span>
</div></header>
{nav}
{body}
<footer><div class="wrap">
  <p><strong>Demiton maintains this record and sells software that protects against these diseases.</strong> That is a commercial interest, stated in <a href="{REPO}/blob/main/GOVERNANCE.md">GOVERNANCE.md</a>. Every change goes through a public pull request.</p>
  <p>Data <a href="{REPO}/blob/main/LICENSE">CC BY 4.0</a>, credit "disease-economics by Demiton". Code MIT. Quoted passages remain their authors'. Release {e(release)}, updated {e(today)}.
  <a href="https://demiton.io/privacy-policy">Privacy policy</a> · <button type="button" data-cookie-reset>Analytics settings</button></p>
</div></footer>
<script>{COMMON_JS}</script>
{scripts}
</body>
</html>
"""


def disease_nav(current: str | None = None, anchors: bool = False) -> str:
    items = [(k, n, s) for k, n, s, *_ in DISEASES] + [("context", "Context", "context")]
    links = "".join(
        f'<a href="{"#" + k if anchors else "/" + s + "/"}"{" aria-current=page" if k == current else ""}>{e(n)}</a>'
        for k, n, s in items)
    if anchors:
        links += '<a href="#sources">Sources</a>'
    return links


# ---- pages ----------------------------------------------------------------------------------------

def render(release: str, today: str, ctx: dict | None = None) -> str:
    """The index: every figure, filterable, with each disease's answer and a link to its page."""
    ctx = ctx or load()
    sources, current = ctx["sources"], ctx["current"]
    sections = []
    for key, name, slug, blurb, _ in DISEASES:
        rows = ctx["by_d"][key]
        head = next((r for r in rows if r["is_headline"]), None)
        head_line = ""
        if head:
            num, of = figure(head)
            head_line = (f'<p class="headline-line" data-for="{e(head["id"])}">Headline: <span class="mono">{e(num)}</span> '
                         f'{e(of)}, <span class="muted">{e(head["confidence"])} confidence</span></p>')
        sections.append(f"""
<section id="{key}">
  <h2>{e(name)}: what it costs a contractor</h2>
  <p class="blurb">{e(blurb)}</p>
  <p class="answer">{e(answer(key, ctx))}</p>
  <p class="more"><a href="/{slug}/">{e(name)} statistics: the table, questions and answers</a></p>
  {head_line}
  {''.join(finding_card(r, sources) for r in rows)}
  <p class="empty" hidden>No {e(name.lower())} figures match this filter.</p>
</section>""")
    sections.append(f"""
<section id="context">
  <h2>Context</h2>
  <p class="blurb">Figures that frame a disease rather than measure it, such as a typical planned margin. Never a headline.</p>
  {''.join(finding_card(r, sources) for r in ctx['context'])}
  <p class="empty" hidden>No context figures match this filter.</p>
</section>""")
    src_items = "".join(
        f'<li id="src-{e(slug)}" data-j="{e(" ".join(s["jurisdictions"]))}" data-i="{e(" ".join(s["industries"]))}">'
        f'<span class="org">{e(s["organisation"])} ({e(s["year"])})</span>, '
        + (f'<a href="{e(s["url"])}" rel="noopener">{e(s["title"])}</a>' if s.get("url") else e(s["title"]))
        + (' <span class="tag warn">second-hand</span>' if s["access"] == "secondary" else "")
        + f' <span class="muted">{e(", ".join(s["jurisdictions"]))}</span>'
        f' · <a href="{REPO}/blob/main/sources/{e(slug)}.md">record</a></li>'
        for slug, s in sorted(sources.items(), key=lambda kv: (kv[1]["organisation"].lower(), kv[1]["year"])))
    sections.append(f"""
<section id="sources">
  <h2>Sources</h2>
  <p class="blurb">Every paper, report and data release the figures come from. Sources read second-hand are marked.</p>
  <ul class="sources">{src_items}</ul>
</section>""")

    body = f"""
<div class="wrap hero">
  <h1>What rework, cost overruns, missed claims, disputes and lapsed compliance cost a construction contractor</h1>
  <p class="lede">Published research on five costly problems on a construction job, with Queensland and Australia first. Each figure shows its source, the page it was read on, how sure we are, and what it is not. Anyone can dispute a figure, or add evidence.</p>
  <p class="updated">Updated {e(today)} · maintained by <a href="https://demiton.io">Demiton</a> · <a href="{REPO}/blob/main/METHOD.md">method</a></p>
  <div class="stats">
    <div class="stat"><b>{len(current)}</b><span>figures</span></div>
    <div class="stat"><b>{len(sources)}</b><span>sources</span></div>
    <div class="stat"><b>{ctx['n_second']}</b><span>read second-hand</span></div>
    <a class="stat" href="{REPO}/releases/tag/{e(release)}"><b>{e(release)}</b><span>release</span></a>
    <a class="stat" href="{REPO}/tree/main/schema" title="The schema every figure is validated against"><b>{e(ctx['schema_version'])}</b><span>schema version</span></a>
  </div>
  <div class="cta">
    <a class="btn primary" href="{REPO}/issues/new?template=new-evidence.yml">Suggest a source</a>
    <a class="btn" href="{REPO}/blob/main/CONTRIBUTING.md">Contribute on GitHub</a>
    <a class="btn" href="/findings.csv" download>Download CSV</a>
    <a class="btn" href="/findings.json" download>Download JSON</a>
  </div>
  <p class="nogh">No GitHub account? Email sources or disputes to <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>
  <div class="method">
    <strong>How to read a figure.</strong>
    <ul>
      <li><b>Contractor loss</b> is money the contractor loses. <b>Money at stake</b> is claimable, held or in dispute: not necessarily lost. Owner's and societal money is shown and never counted as the contractor's.</li>
      <li><b>Confidence</b> follows one published rule: high means read at source and free of the known weaknesses; moderate means one organisation's data, people's own estimates, or a named sampling problem; low means second-hand, unverifiable, or a model.</li>
      <li>Only a share of contract value is ever multiplied by a contract value. Everything else is shown as it is. <a href="{REPO}/blob/main/METHOD.md">The full method</a>.</li>
    </ul>
  </div>
</div>
<main class="wrap" id="main" tabindex="-1">
{''.join(sections)}
</main>"""
    nav = (f'<nav class="diseases" aria-label="Diseases"><div class="wrap">{disease_nav(anchors=True)}'
           f'<button type="button" class="f-toggle" id="f-toggle" aria-expanded="false" aria-controls="f-bar">Filter</button></div>'
           f'{filter_bar(ctx["data"])}</nav>')
    dataset = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "disease-economics: what published research says the diseases of a construction job cost",
        "description": f"{len(current)} figures from published research on what rework, cost overruns, missed claims, disputes "
                       "and lapsed compliance cost construction contractors, each with its source, the page it was read on, "
                       "a confidence grade and a caveat. Open to dispute on GitHub.",
        "url": SITE + "/", "sameAs": REPO, "version": release, "dateModified": today,
        "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Demiton", "url": "https://demiton.io"},
        "keywords": ["construction", "civil engineering", "rework", "cost overrun", "construction disputes",
                     "security of payment", "adjudication", "Queensland", "Australia"],
        "spatialCoverage": "Australia",
        "hasPart": [{"@type": "WebPage", "name": f"{n} statistics", "url": f"{SITE}/{s}/"} for _, n, s, *_ in DISEASES],
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE + "/findings.csv"},
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": SITE + "/findings.json"},
        ],
    }
    return layout(
        title="Construction rework, overrun and dispute statistics | Demiton",
        description=(f"{len(current)} sourced figures on what rework, cost overruns, missed claims, disputes and lapsed "
                     "compliance cost construction contractors in Australia and Queensland. Every figure graded and open to dispute."),
        og_title="What the diseases of a construction job cost, and where every figure came from",
        path="/", body=body, today=today, release=release, json_ld=[ld(dataset)], nav=nav,
        scripts=f"<script>{FILTER_JS}</script>")


def breadcrumbs(items: list[tuple[str, str]]) -> tuple[str, str]:
    html = " / ".join(f'<a href="{u}">{e(n)}</a>' for n, u in items[:-1]) + f" / {e(items[-1][0])}"
    data = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + u} for i, (n, u) in enumerate(items)]}
    return f'<p class="crumbs">{html}</p>', ld(data)


def disease_page(key: str, ctx: dict, release: str, today: str) -> str:
    name = NAME[key]
    slug = SLUG[key]
    rows = ctx["by_d"][key] if key != "context" else ctx["context"]
    sources = ctx["sources"]
    blurb = next((b for k, _, _, b, _ in DISEASES if k == key),
                 "Figures that frame a disease rather than measure it, such as a typical planned margin. Never a headline.")
    crumbs, crumbs_ld = breadcrumbs([("Research", "/"), (f"{name} statistics", f"/{slug}/")])
    faq_html, faq_ld = "", []
    if key != "context":
        pairs = qa(key, ctx)
        faq_html = '<h2>Questions and answers</h2><div class="faq">' + "".join(
            f'<h3 class="q">{e(q)}</h3><p>{e(a)}</p>' for q, a in pairs) + "</div>"
        faq_ld = [ld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]})]
    title = (f"{name} statistics: what it costs a construction contractor | Demiton" if key != "context"
             else "Context figures for construction cost research | Demiton")
    lead = answer(key, ctx) if key != "context" else blurb
    body = f"""
<main class="wrap" id="main" tabindex="-1">
  {crumbs}
  <h1>{e(name)}{': what it costs a construction contractor' if key != 'context' else ''}</h1>
  <p class="blurb">{e(blurb)}</p>
  <p class="answer">{e(lead)}</p>
  <p class="updated">Updated {e(today)} · release {e(release)} · <a href="/">all five diseases</a></p>
  <h2>Every figure</h2>
  {table(rows, sources)}
  {faq_html}
  <h2>The evidence</h2>
  {''.join(finding_card(r, sources) for r in rows)}
</main>"""
    nav = f'<nav class="diseases" aria-label="Diseases"><div class="wrap">{disease_nav(current=key)}</div></nav>'
    return layout(title=title, description=lead[:300], path=f"/{slug}/", body=body, today=today, release=release,
                  json_ld=[crumbs_ld] + faq_ld, nav=nav)


def finding_page(row: dict, ctx: dict, release: str, today: str) -> str:
    sources = ctx["sources"]
    key = row["disease_key"] or "context"
    name, slug = NAME[key], SLUG[key]
    num, of = figure(row)
    path = page_url(row)
    crumbs, crumbs_ld = breadcrumbs([("Research", "/"), (f"{name} statistics", f"/{slug}/"), (row["label"], path)])
    quote = sentence(row, sources)
    data = {
        "@context": "https://schema.org", "@type": "Dataset", "name": row["label"],
        "description": f"{quote} {row['sample_note']} What it is not: {row['caveat']}",
        "url": SITE + path, "isPartOf": {"@type": "Dataset", "name": "disease-economics", "url": SITE + "/"},
        "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "Demiton", "url": "https://demiton.io"},
        "dateModified": today, "version": release, "spatialCoverage": place(row["jurisdictions"]),
        "variableMeasured": {"@type": "PropertyValue", "name": row["label"], "value": row["exposure_value"], "unitText": of},
        "citation": [{"@type": "CreativeWork", "name": sources[c["source"]]["title"],
                      "author": sources[c["source"]]["organisation"], "datePublished": str(sources[c["source"]]["year"]),
                      "url": sources[c["source"]].get("url")} for c in row["_citations"]],
    }
    body = f"""
<main class="wrap" id="main" tabindex="-1">
  {crumbs}
  <h1>{e(row['label'])}</h1>
  <div class="big"><span class="num">{e(num)}</span><span class="of">{e(of)}</span></div>
  <div class="flags">{flags(row)}</div>
  <p class="answer">{e(quote)}</p>
  <div class="solo">{finding_body(row, sources)}</div>
  <p class="more"><a href="/{slug}/">Every {e(name.lower())} figure</a> · <a href="/">all five diseases</a></p>
</main>"""
    nav = f'<nav class="diseases" aria-label="Diseases"><div class="wrap">{disease_nav(current=key)}</div></nav>'
    return layout(title=f"{short_title(row['label'])} | Demiton", og_title=f"{num} {of}: {row['label']}",
                  description=quote[:300], path=path,
                  body=body, today=today, release=release, json_ld=[crumbs_ld, ld(data)], nav=nav)


def llms_txt(ctx: dict, release: str, today: str) -> tuple[str, str]:
    """llms.txt (a map of the corpus) and llms-full.txt (every figure as plain text)."""
    lines = [
        "# disease-economics (Demiton research)",
        "",
        f"> What published research says rework, cost overruns, missed claims, disputes and lapsed compliance cost "
        f"construction contractors, with Queensland and Australia first. {len(ctx['current'])} figures, each with its "
        f"source, the page it was read on, a confidence grade and a caveat. Release {release}, updated {today}. "
        "Licensed CC BY 4.0: credit 'disease-economics by Demiton'.",
        "",
        "## Diseases",
    ]
    for key, name, slug, blurb, _ in DISEASES:
        lines.append(f"- [{name} statistics]({SITE}/{slug}/): {blurb}")
    lines += ["- [Context figures](" + SITE + "/context/): planned margins and overheads that frame the diseases.",
              "", "## Data",
              f"- [All findings, CSV]({SITE}/findings.csv)",
              f"- [All findings, JSON]({SITE}/findings.json)",
              f"- [Every figure as plain text]({SITE}/llms-full.txt)",
              "", "## Method and governance",
              f"- [METHOD.md]({REPO}/blob/main/METHOD.md): what the kinds, units and confidence grades mean",
              f"- [GOVERNANCE.md]({REPO}/blob/main/GOVERNANCE.md): who decides, and Demiton's commercial interest",
              f"- [Schema]({REPO}/tree/main/schema): the versioned JSON Schemas every figure is validated against",
              f"- [Source repository]({REPO})"]
    full = [f"# disease-economics, every figure (release {release}, {today})", "",
            "Figures are estimates with stated confidence, not measurements. Only a share of contract value may be "
            "multiplied by a contract value. Cite as 'disease-economics by Demiton' with the figure's URL.", ""]
    for key, name, *_ in DISEASES + [("context", "Context", "context", "", "")]:
        rows = [r for r in (ctx["context"] if key == "context" else ctx["by_d"][key]) if r.get("status") != "withdrawn"]
        full.append(f"## {name}")
        full.append("")
        for r in rows:
            full.append(f"- {sentence(r, ctx['sources'])}")
            full.append(f"  What it is: {figure(r)[0]} {r['exposure_basis']}. Sample: {r['sample_note']}")
            full.append(f"  What it is not: {r['caveat']}")
            full.append(f"  URL: {SITE}{page_url(r)}")
        full.append("")
    return "\n".join(lines) + "\n", "\n".join(full) + "\n"


def sitemap(paths: list[str], today: str) -> str:
    urls = "".join(f"<url><loc>{e(SITE + p)}</loc><lastmod>{today}</lastmod></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


ROBOTS = f"""# research.demiton.io: open data (CC BY 4.0). Search engines and AI crawlers are welcome.
User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: CCBot
Allow: /

Sitemap: {SITE}/sitemap.xml
"""


def build(out: Path, release: str, today: str) -> list[str]:
    """Write the whole site to `out`; return the page paths."""
    write(out, release)
    ctx = load()
    pages = {"/": render(release, today, ctx)}
    for key, *_ in DISEASES:
        pages[f"/{SLUG[key]}/"] = disease_page(key, ctx, release, today)
    pages["/context/"] = disease_page("context", ctx, release, today)
    for r in ctx["data"]:
        if r.get("status") != "withdrawn":
            pages[page_url(r)] = finding_page(r, ctx, release, today)
    for path, html in pages.items():
        target = out / path.strip("/") / "index.html" if path != "/" else out / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)
    (out / "sitemap.xml").write_text(sitemap(list(pages), today))
    (out / "robots.txt").write_text(ROBOTS)
    short, full = llms_txt(ctx, release, today)
    (out / "llms.txt").write_text(short)
    (out / "llms-full.txt").write_text(full)
    for asset in sorted((ROOT / "assets").glob("*")):
        shutil.copy(asset, out / asset.name)
    return list(pages)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--release", default="unreleased")
    args = ap.parse_args()
    errors, _ = validate(ROOT)
    if errors:
        print("the corpus does not validate; run scripts/validate.py", file=sys.stderr)
        return 1
    pages = build(Path(args.out), args.release, date.today().isoformat())
    print(f"site -> {args.out}: {len(pages)} pages ({args.release})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
