"""Build the ledger: one row per finding, joined to its source of record. Deterministic.

    python scripts/build_ledger.py --out dist --release v1

Writes <out>/findings.json and <out>/findings.csv. Not committed: release.yml attaches them to the
GitHub release, and the platform pins a release rather than reading main.
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
    """Write findings.json and findings.csv to `out`; return the rows. Shared with build_site.py."""
    out.mkdir(parents=True, exist_ok=True)
    data = rows(ROOT)
    (out / "findings.json").write_text(json.dumps({"release": release, "findings": data}, indent=2) + "\n")
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
