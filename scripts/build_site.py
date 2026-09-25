"""Build research.demiton.io: one static page rendered from the corpus, plus the ledger files.

    python scripts/build_site.py --out site --release v3

Everything on the page comes from the same files the ledger is built from, so the site cannot
say anything the record does not. No framework and no client-side script: findings expand with
native <details>.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ledger import write  # noqa: E402
from validate import ROOT, load_corpus, validate  # noqa: E402

REPO = "https://github.com/demitonapp/disease-economics"

#: Research-cost order (the order the docs long read argues for), with the public names.
DISEASES = [
    ("rework_signal", "Rework", "Work done twice: poured to the wrong level, built off the wrong drawing, redone after a failed test."),
    ("overrun_signal", "Cost drift", "The job costing more than it was priced at, and how much of that the contractor carries."),
    ("claim_window", "Missed claims", "Variations, extensions of time, delay costs and retention the contract allowed and nobody claimed in time. Includes weather."),
    ("evidence_gap", "Disputes", "Money fought over, what it costs to fight, and how much is recovered."),
    ("compliance_gate", "Lapsed compliance", "Accidents, lapsed licences and insurance, and the cost of breaching the obligations that come with the job."),
]

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
}

CURRENCY = {"AUD": "A$", "USD": "US$", "NZD": "NZ$", "GBP": "£", "EUR": "€"}
PER = {"per_wet_day": "per wet day", "per_incident": "per incident"}
CONFIDENCE_ORDER = {"high": 0, "moderate": 1, "low": 2}


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


def e(s) -> str:
    return escape(str(s)) if s is not None else ""


def source_line(slug: str, src: dict, location: str | None) -> str:
    sec = ' <span class="tag warn">second-hand</span>' if src["access"] == "secondary" else ""
    link = f'<a href="{e(src["url"])}" rel="noopener">{e(src["title"])}</a>' if src.get("url") else e(src["title"])
    free = f' · <a href="{e(src["free_copy_url"])}" rel="noopener">free copy</a>' if src.get("free_copy_url") else ""
    via = f'<div class="via">Read via: {e(src["read_via"])}</div>' if src["access"] == "secondary" and src.get("read_via") else ""
    return (
        f'<li><span class="org">{e(src["organisation"])} ({e(src["year"])})</span>, {link}{free}{sec}'
        f'<div class="loc">{e(location or src["location"])} · <a href="{REPO}/blob/main/sources/{e(slug)}.md">source record</a></div>{via}</li>'
    )


def finding_card(row: dict, sources: dict, path: str) -> str:
    num, of = figure(row)
    kind_label, kind_help = KIND.get(row["exposure_kind"], (row["exposure_kind"], ""))
    status = row.get("status") or "current"
    flags = []
    if row["is_headline"]:
        flags.append('<span class="tag headline">Headline</span>')
    flags.append(f'<span class="tag conf-{e(row["confidence"])}" title="METHOD.md Section 4">{e(row["confidence"]).capitalize()} confidence</span>')
    flags.append(f'<span class="tag kind" title="{e(kind_help)}">{e(kind_label)}</span>')
    if row.get("source_secondary"):
        flags.append('<span class="tag warn">Second-hand</span>')
    if status == "disputed":
        flags.append(f'<a class="tag bad" href="{e(row.get("dispute_url"))}">Disputed</a>')
    if status == "withdrawn":
        flags.append('<span class="tag bad">Withdrawn</span>')
    cites = []
    for c in row["_citations"]:
        cites.append(source_line(c["source"], sources[c["source"]], c.get("location")))
    considered = "".join(
        f'<li><span class="org">{e(sources[c["source"]]["organisation"])}</span>: {e(c["reason"])}</li>'
        for c in row.get("considered") or []
    )
    history = "".join(
        f'<li><span class="mono">{e(h["changed_on"])}</span> {e(h["reason"])}</li>' for h in row.get("history") or []
    )
    rng = row.get("exposure_range")
    rng_html = ""
    if rng:
        lo, hi = (pct(rng["low"]), pct(rng["high"])) if "ratio" in row["exposure_unit"] else (
            money(rng["low"], row.get("currency") or ""), money(rng["high"], row.get("currency") or ""))
        rng_html = f'<p class="range">Range {e(lo)} to {e(hi)} ({e(rng["kind"].replace("_", " "))})</p>'
    calc = f'<p><strong>Our arithmetic.</strong> {e(row["calculation"])}</p>' if row.get("calculation") else ""
    withdrawn = f'<p class="bad-text"><strong>Withdrawn.</strong> {e(row["withdrawn_reason"])}</p>' if status == "withdrawn" else ""
    basis = row['exposure_basis']
    if basis.startswith('of ') and row['exposure_value'] is not None:
        basis = f'{num} {basis}'
    else:
        basis = basis[:1].upper() + basis[1:]
    where = ", ".join(row["jurisdictions"]) + " · " + ", ".join(row["industries"])
    return f"""
<details class="finding{' is-headline' if row['is_headline'] else ''}{' is-withdrawn' if status == 'withdrawn' else ''}" id="{e(row['id'])}" data-j="{e(' '.join(row['jurisdictions']))}" data-i="{e(' '.join(row['industries']))}">
  <summary>
    <span class="fig"><span class="num">{e(num)}</span><span class="of">{e(of)}</span></span>
    <span class="what"><span class="label">{e(row['label'])}</span><span class="flags">{''.join(flags)}</span></span>
  </summary>
  <div class="body">
    {withdrawn}
    <p><strong>What it is.</strong> {e(basis)}.</p>
    {rng_html}
    <p><strong>Sample.</strong> {e(row['sample_note'])}</p>
    <p><strong>What it is not.</strong> {e(row['caveat'])}</p>
    {calc}
    <h4>Where it came from</h4>
    <ul class="cites">{''.join(cites)}</ul>
    {f'<h4>Considered and set aside</h4><ul class="cites">{considered}</ul>' if considered else ''}
    {f'<h4>History</h4><ul class="hist">{history}</ul>' if history else ''}
    <p class="meta"><span class="mono">{e(row['id'])}</span> · {e(where)} ·
      <a href="{REPO}/blob/main/{e(path)}">the record</a> ·
      <a href="{REPO}/issues/new?template=dispute.yml&amp;finding={e(path)}">dispute this figure</a></p>
  </div>
</details>"""


VOCAB = ROOT / "vocab"


def filter_bar(data: list[dict]) -> str:
    """Jurisdiction and industry selects, built from the codes the findings actually use."""
    import json as _json
    names_j = _json.loads((VOCAB / "jurisdictions.json").read_text())
    names_i = _json.loads((VOCAB / "industries.json").read_text())
    used_j = {j for r in data for j in r["jurisdictions"]}
    used_i = {i for r in data for i in r["industries"]}
    countries = sorted({j.split("-")[0] for j in used_j if j not in ("GLOBAL", "unknown")}, key=lambda c: names_j.get(c, c))
    opts_j = ['<option value="">All jurisdictions</option>']
    for c in countries:
        subs = sorted(j for j in used_j if j.startswith(c + "-"))
        label = names_j.get(c, c) + (" (all)" if subs else "")
        opts_j.append(f'<option value="{e(c)}">{e(label)}</option>')
        for s in subs:
            opts_j.append(f'<option value="{e(s)}">&nbsp;&nbsp;{e(names_j.get(s, s))}</option>')
    for special, label in (("GLOBAL", "Global (no limit claimed)"), ("unknown", "Unknown")):
        if special in used_j:
            opts_j.append(f'<option value="{special}">{label}</option>')
    opts_i = ['<option value="">All industries</option>']
    if used_i & {"F", "F41", "F42", "F43"}:
        opts_i.append('<option value="F">Construction (any)</option>')
    for code in ("F42", "F41", "F43"):
        if code in used_i:
            opts_i.append(f'<option value="{code}">&nbsp;&nbsp;{e(names_i[code])}</option>')
    for special, label in (("ALL", "Not industry-specific"), ("unknown", "Unknown")):
        if special in used_i:
            opts_i.append(f'<option value="{special}">{label}</option>')
    return f"""<div class="filters" hidden><div class="wrap">
  <label>Jurisdiction <select id="f-j">{''.join(opts_j)}</select></label>
  <label>Industry <select id="f-i">{''.join(opts_i)}</select></label>
  <label title="Global figures, national figures for a state, and general-construction or cross-industry figures for an industry"><input type="checkbox" id="f-broad" checked> Include broader evidence</label>
  <button type="button" id="f-reset" hidden>Clear</button>
  <span class="count" id="f-count" aria-live="polite"></span>
</div></div>"""


#: Filtering is the page's only script, and the page works without it: every finding is in the HTML.
FILTER_JS = """
(() => {
  const $ = (id) => document.getElementById(id);
  const bar = document.querySelector('.filters'); bar.hidden = false;
  const selJ = $('f-j'), selI = $('f-i'), broad = $('f-broad'), reset = $('f-reset'), count = $('f-count');
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
  function apply() {
    const vj = selJ.value, vi = selI.value, b = broad.checked;
    const keep = (el) => matchJ(list(el, 'j'), vj, b) && matchI(list(el, 'i'), vi, b);
    let shown = 0, total = 0;
    document.querySelectorAll('details.finding').forEach((d) => {
      const ok = keep(d); d.hidden = !ok;
      if (!d.classList.contains('is-withdrawn')) { total++; if (ok) shown++; }
    });
    document.querySelectorAll('main section').forEach((s) => {
      const empty = s.querySelector('.empty');
      if (empty) empty.hidden = !!s.querySelector('details.finding:not([hidden])');
    });
    document.querySelectorAll('ul.sources li').forEach((li) => { li.hidden = !keep(li); });
    const on = !!(vj || vi);
    count.textContent = on ? `Showing ${shown} of ${total} figures` : `${total} figures`;
    reset.hidden = !on;
    const p = new URLSearchParams();
    if (vj) p.set('j', vj); if (vi) p.set('i', vi); if (!b) p.set('broad', '0');
    history.replaceState(null, '', (p.toString() ? '?' + p : location.pathname) + location.hash);
  }
  [selJ, selI, broad].forEach((el) => el.addEventListener('change', apply));
  reset.addEventListener('click', () => { selJ.value = ''; selI.value = ''; broad.checked = true; apply(); });
  apply();
})();
"""


def order(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (
        not r["is_headline"], r.get("status") == "withdrawn", CONFIDENCE_ORDER.get(r["confidence"], 9), r["id"]))


def render(release: str, today: str) -> str:
    _, sources, findings, _ = load_corpus(ROOT)
    from build_ledger import rows as ledger_rows
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
    n_sources = len(sources)
    n_second = sum(1 for s in sources.values() if s["access"] == "secondary")
    by_d = {k: [r for r in data if r["disease_key"] == k] for k, _, _ in DISEASES}

    filters = filter_bar(data)
    nav = "".join(f'<a href="#{k}">{e(name)}</a>' for k, name, _ in DISEASES) + '<a href="#context">Context</a><a href="#sources">Sources</a>'
    sections = []
    for key, name, blurb in DISEASES:
        rows = order(by_d[key])
        head = next((r for r in rows if r["is_headline"]), None)
        head_line = ""
        if head:
            num, of = figure(head)
            head_line = f'<p class="headline-line">Headline: <span class="mono">{e(num)}</span> {e(of)}, <span class="muted">{e(head["confidence"])} confidence</span></p>'
        cards = "".join(finding_card(r, sources, r["_path"]) for r in rows)
        sections.append(f"""
<section id="{key}">
  <h2>{e(name)}</h2>
  <p class="blurb">{e(blurb)}</p>
  {head_line}
  {cards}
  <p class="empty" hidden>No {e(name.lower())} figures match this filter.</p>
</section>""")
    ctx = order([r for r in data if r["family"] == "context"])
    sections.append(f"""
<section id="context">
  <h2>Context</h2>
  <p class="blurb">Figures that frame a disease rather than measure it, such as a typical planned margin. Never a headline.</p>
  {''.join(finding_card(r, sources, r['_path']) for r in ctx)}
  <p class="empty" hidden>No context figures match this filter.</p>
</section>""")
    src_items = "".join(
        f'<li id="src-{e(slug)}" data-j="{e(" ".join(s["jurisdictions"]))}" data-i="{e(" ".join(s["industries"]))}"><span class="org">{e(s["organisation"])} ({e(s["year"])})</span>, '
        f'{"<a href=" + chr(34) + e(s["url"]) + chr(34) + " rel=noopener>" + e(s["title"]) + "</a>" if s.get("url") else e(s["title"])}'
        f'{" <span class=" + chr(34) + "tag warn" + chr(34) + ">second-hand</span>" if s["access"] == "secondary" else ""}'
        f' <span class="muted">{e(", ".join(s["jurisdictions"]))}</span>'
        f' · <a href="{REPO}/blob/main/sources/{e(slug)}.md">record</a></li>'
        for slug, s in sorted(sources.items(), key=lambda kv: (kv[1]["organisation"].lower(), kv[1]["year"]))
    )
    sections.append(f"""
<section id="sources">
  <h2>Sources</h2>
  <p class="blurb">Every paper, report and data release the figures come from. {n_second} of {n_sources} were read second-hand, and are marked.</p>
  <ul class="sources">{src_items}</ul>
</section>""")

    return f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Disease economics | Demiton research</title>
<meta name="description" content="What published research says rework, cost drift, missed claims, disputes and lapsed compliance cost a construction contractor, and where every figure came from.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%230B1220'/%3E%3Crect x='7' y='7' width='18' height='18' fill='none' stroke='%23F9FAFB' stroke-width='3'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Newsreader:opsz,wght@6..72,500&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #0B1220; --surface: #111827; --panel: #1F2937; --border: #374151;
  --text: #F9FAFB; --muted: #9CA3AF; --steel: #5B8DB8; --violet: #7C3AED; --violet-text: #A78BFA;
  --green: #059669; --amber: #D97706; --red: #DC2626;
  --serif: "Newsreader", Georgia, serif; --sans: "Inter", system-ui, sans-serif; --mono: "IBM Plex Mono", ui-monospace, monospace;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.6 var(--sans); }}
a {{ color: var(--steel); }}
a:hover {{ color: #7FA7CC; }}
a:focus-visible, summary:focus-visible {{ outline: 2px solid var(--violet-text); outline-offset: 2px; }}
.wrap {{ max-width: 960px; margin: 0 auto; padding: 0 16px; }}
header.top {{ border-bottom: 1px solid var(--border); }}
header.top .wrap {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding-top: 16px; padding-bottom: 16px; }}
.wordmark {{ font: 500 14px var(--sans); letter-spacing: .15em; color: var(--text); text-decoration: none; }}
.top-links a {{ margin-left: 16px; font-size: 14px; }}
.hero {{ padding-top: 56px; padding-bottom: 24px; }}
h1 {{ font: 500 clamp(34px, 6vw, 56px)/1.1 var(--serif); margin: 0 0 16px; }}
h2 {{ font: 500 clamp(26px, 4vw, 36px)/1.2 var(--serif); margin: 0 0 8px; }}
h4 {{ font: 600 13px var(--sans); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 20px 0 8px; }}
.lede {{ font-size: 19px; color: #D1D5DB; max-width: 44em; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 8px; }}
.stat {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; min-width: 120px; }}
.stat b {{ display: block; font: 500 24px var(--mono); }}
.stat span {{ font-size: 13px; color: var(--muted); }}
.cta {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 0; }}
.btn {{ display: inline-block; padding: 10px 16px; border-radius: 6px; border: 1px solid var(--border); color: var(--text); text-decoration: none; font-weight: 500; font-size: 15px; }}
.btn.primary {{ background: var(--violet); border-color: var(--violet); color: #fff; }}
.btn.primary:hover {{ background: #6D28D9; color: #fff; }}
.btn:hover {{ border-color: var(--steel); color: var(--text); }}
nav.diseases {{ position: sticky; top: 0; z-index: 2; background: rgba(11,18,32,.95); border-bottom: 1px solid var(--border); backdrop-filter: blur(6px); }}
nav.diseases .wrap {{ display: flex; gap: 20px; overflow-x: auto; padding-top: 12px; padding-bottom: 12px; white-space: nowrap; }}
nav.diseases a {{ color: var(--muted); text-decoration: none; font-size: 14px; font-weight: 500; }}
nav.diseases a:hover {{ color: var(--text); }}
section {{ padding: 48px 0 8px; scroll-margin-top: 110px; }}
.filters {{ border-top: 1px solid var(--border); }}
.filters .wrap {{ display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; padding-top: 10px; padding-bottom: 10px; font-size: 14px; }}
.filters label {{ display: inline-flex; align-items: center; gap: 8px; color: var(--muted); }}
.filters select {{ background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font: 14px var(--sans); max-width: 60vw; }}
.filters input[type=checkbox] {{ accent-color: var(--violet); width: 16px; height: 16px; }}
.filters .count {{ margin-left: auto; color: var(--muted); font-family: var(--mono); font-size: 13px; }}
.filters button {{ background: none; border: 0; color: var(--steel); font: 14px var(--sans); cursor: pointer; padding: 0; }}
.empty {{ color: var(--muted); font-style: italic; }}
[hidden] {{ display: none !important; }}
.blurb {{ color: var(--muted); margin: 0 0 8px; max-width: 44em; }}
.headline-line {{ margin: 0 0 16px; }}
.muted {{ color: var(--muted); }}
.mono {{ font-family: var(--mono); }}
.finding {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin: 10px 0; }}
.finding.is-headline {{ border-color: var(--steel); }}
.finding.is-withdrawn {{ opacity: .6; }}
.finding summary {{ list-style: none; cursor: pointer; display: grid; grid-template-columns: 150px 1fr; gap: 16px; padding: 16px; }}
.finding summary::-webkit-details-marker {{ display: none; }}
.fig {{ display: flex; flex-direction: column; }}
.num {{ font: 500 26px/1.1 var(--mono); }}
.of {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
.label {{ display: block; font-weight: 500; }}
.flags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
.tag {{ font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--muted); text-decoration: none; }}
.tag.headline {{ border-color: var(--steel); color: var(--text); }}
.tag.conf-high {{ border-color: var(--green); color: #6EE7B7; }}
.tag.conf-moderate {{ border-color: var(--amber); color: #FCD34D; }}
.tag.conf-low {{ border-color: var(--red); color: #FCA5A5; }}
.tag.warn {{ border-color: var(--amber); color: #FCD34D; }}
.tag.bad {{ border-color: var(--red); color: #FCA5A5; }}
.bad-text {{ color: #FCA5A5; }}
.finding .body {{ padding: 0 16px 16px; border-top: 1px solid var(--border); }}
.finding .body p {{ margin: 12px 0; max-width: 48em; }}
.cites, .hist, .sources {{ margin: 0; padding-left: 18px; }}
.cites li, .sources li {{ margin: 6px 0; }}
.org {{ font-weight: 500; }}
.loc, .via {{ font-size: 13px; color: var(--muted); }}
.meta {{ font-size: 13px; color: var(--muted); border-top: 1px solid var(--border); padding-top: 12px; }}
.range {{ font-family: var(--mono); font-size: 14px; }}
.method {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-top: 16px; }}
.method ul {{ margin: 8px 0 0; padding-left: 18px; }}
footer {{ border-top: 1px solid var(--border); margin-top: 64px; padding: 32px 0 48px; color: var(--muted); font-size: 14px; }}
@media (max-width: 640px) {{
  .finding summary {{ grid-template-columns: 1fr; gap: 8px; }}
  .top-links a:not(:last-child) {{ display: none; }}
}}
</style>
</head>
<body>
<header class="top"><div class="wrap">
  <a class="wordmark" href="https://demiton.io">DEMITON</a>
  <span class="top-links"><a href="https://docs.demiton.io/start-here/disease-priority">The long read</a><a href="{REPO}">GitHub</a></span>
</div></header>
<div class="wrap hero">
  <h1>What the diseases of a construction job cost, and where every figure came from</h1>
  <p class="lede">Published research on five costly problems on a construction job: rework, cost drift, missed claims, disputes and lapsed compliance. Each figure shows its source, the page it was read on, how sure we are, and what it is not. Anyone can dispute a figure, or add evidence, on GitHub.</p>
  <div class="stats">
    <div class="stat"><b>{len(current)}</b><span>figures</span></div>
    <div class="stat"><b>{n_sources}</b><span>sources</span></div>
    <div class="stat"><b>{n_second}</b><span>read second-hand</span></div>
    <div class="stat"><b>{e(release)}</b><span>release</span></div>
  </div>
  <div class="cta">
    <a class="btn primary" href="{REPO}/blob/main/CONTRIBUTING.md">Add evidence</a>
    <a class="btn" href="findings.csv" download>Download CSV</a>
    <a class="btn" href="findings.json" download>Download JSON</a>
  </div>
  <div class="method">
    <strong>How to read a figure.</strong>
    <ul>
      <li><b>Contractor loss</b> is money the contractor loses. <b>Money at stake</b> is claimable, held or in dispute: not necessarily lost. Owner's and societal money is shown and never counted as the contractor's.</li>
      <li><b>Confidence</b> follows one published rule: high means read at source and free of the known weaknesses; moderate means one organisation's data, people's own estimates, or a named sampling problem; low means second-hand, unverifiable, or a model.</li>
      <li>Only a share of contract value is ever multiplied by a contract value. Everything else is shown as it is. <a href="{REPO}/blob/main/METHOD.md">The full method</a>.</li>
    </ul>
  </div>
</div>
<nav class="diseases" aria-label="Diseases"><div class="wrap">{nav}</div>{filters}</nav>
<main class="wrap">
{''.join(sections)}
</main>
<footer><div class="wrap">
  <p><strong>Demiton maintains this record and sells software that protects against these diseases.</strong> That is a commercial interest, stated in <a href="{REPO}/blob/main/GOVERNANCE.md">GOVERNANCE.md</a>. Every change goes through a public pull request.</p>
  <p>Data <a href="{REPO}/blob/main/LICENSE">CC BY 4.0</a>, credit "disease-economics by Demiton". Code MIT. Quoted passages remain their authors'. Release {e(release)}, built {e(today)}.</p>
</div></footer>
<script>{FILTER_JS}</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--release", default="unreleased")
    args = ap.parse_args()
    errors, _ = validate(ROOT)
    if errors:
        print("the corpus does not validate; run scripts/validate.py", file=sys.stderr)
        return 1
    out = Path(args.out)
    write(out, args.release)
    (out / "index.html").write_text(render(args.release, date.today().isoformat()))
    print(f"site -> {out}/index.html ({args.release})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
