"""Build the ledger: one row per finding, joined to its source of record. Deterministic.

    python scripts/build_ledger.py --out dist --release v1

Writes <out>/findings.json and <out>/findings.csv (the ledger the product pins by release), and
<out>/corpus.json: the ledger plus every citation, every source and the vocabulary, which is what
research.demiton.io is built from. Not committed: release.yml attaches all three to the GitHub
release, and publish.yml keeps them current on the rolling `data-latest` release.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import ROOT, load_corpus, validate  # noqa: E402

COLUMNS = [
    "id", "family", "disease_key", "metric_key", "label", "exposure_value", "exposure_unit", "denominator",
    "currency", "price_year", "exposure_basis", "exposure_kind", "confidence", "is_headline", "exposure_range",
    "derivation", "calculation", "sample_note", "caveat", "status", "dispute_url", "withdrawn_reason",
    "sources", "considered", "history", "jurisdictions", "industries",
    # The source of record (the first citation), under the names the product already reads.
    "source_org", "source_title", "source_url", "source_location", "source_year", "source_secondary",
]


def rows(root: Path = ROOT) -> list[dict]:
    _, sources, findings, _ = load_corpus(root)
    out = []
    for path, f in findings.items():
        parts = Path(path).parts
        family = "context" if parts[0] == "context" else "disease"
        disease = None if family == "context" else parts[1]
        metric = Path(path).stem
        cites = [c if isinstance(c, dict) else {"source": c} for c in f["sources"]]
        cited = [sources[c["source"]] for c in cites]
        record, first = cited[0], cites[0]
        row = {k: f.get(k) for k in COLUMNS}
        row.update(
            id=f"{family if disease is None else disease}/{metric}",
            family=family, disease_key=disease, metric_key=metric,
            is_headline=bool(f.get("is_headline")),
            sources=[c["source"] for c in cites],
            jurisdictions=sorted({j for s in cited for j in s["jurisdictions"]}),
            industries=sorted({i for s in cited for i in s["industries"]}),
            source_org=record["organisation"], source_title=record["title"], source_url=record.get("url"),
            source_location=first.get("location", record["location"]), source_year=record["year"],
            source_secondary=record["access"] == "secondary",
            _path=path, _citations=cites,
        )
        out.append(row)
    return sorted(out, key=lambda r: r["id"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--release", default="unreleased")
    args = ap.parse_args()
    errors, _ = validate(ROOT)
    if errors:
        print("the corpus does not validate; run scripts/validate.py", file=sys.stderr)
        return 1
    data = write(Path(args.out), args.release)
    print(f"{len(data)} findings -> {args.out}/findings.json, {args.out}/findings.csv ({args.release})")
    return 0


def write(out: Path, release: str) -> list[dict]:
    """Write findings.json, findings.csv and corpus.json to `out`; return the ledger rows."""
    out.mkdir(parents=True, exist_ok=True)
    full = rows(ROOT)
    data = [{k: v for k, v in r.items() if not k.startswith("_")} for r in full]
    schemas = {p.name: json.loads(p.read_text()).get("x-schema-version") for p in sorted((ROOT / "schema").glob("*.schema.json"))}
    _, sources, _, _ = load_corpus(ROOT)
    codes = {x for s in sources.values() for c in s["jurisdictions"] + s["industries"] for x in (c, c.split("-")[0])}
    vocab = {name: {k: v for k, v in json.loads((ROOT / "vocab" / f"{name}.json").read_text()).items() if k in codes}
             for name in ("jurisdictions", "industries")}
    corpus = {
        "release": release, "schema_versions": schemas,
        "findings": [{**d, "path": r["_path"], "citations": r["_citations"]} for d, r in zip(data, full)],
        "sources": sources, "vocab": vocab,
    }
    (out / "corpus.json").write_text(json.dumps(corpus, indent=2, default=str) + "\n")
    (out / "findings.json").write_text(json.dumps({"release": release, "schema_versions": schemas, "findings": data}, indent=2) + "\n")
    with (out / "findings.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["release", *COLUMNS])
        w.writeheader()
        for r in data:
            w.writerow({"release": release, **{
                k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in r.items()
            }})
    return data


if __name__ == "__main__":
    sys.exit(main())
