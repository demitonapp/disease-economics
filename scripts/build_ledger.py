"""Build the ledger: one row per finding, joined to its source of record. Deterministic.

    python scripts/build_ledger.py --out dist --release v1

Writes <out>/findings.json and <out>/findings.csv (the ledger the product pins by release), and
<out>/corpus.json: the ledger plus every citation, every source, the vocabulary and the history of
every schema and record (from git), which is what
research.demiton.io is built from. Not committed: release.yml attaches all three to the GitHub
release, and publish.yml keeps them current on the rolling `data-latest` release.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate import ROOT, SCHEMA_DIR, load_corpus, split_frontmatter, validate  # noqa: E402

#: Schemas that once lived at schema/<name>.schema.json before spec 09 P4 pinned them from
#: demitonapp/registers instead - kept so `history()` can still walk their pre-migration git log.
SCHEMA_NAMES = ("finding", "source", "protection")

COLUMNS = [
    "id", "family", "disease_key", "metric_key", "subtype", "label", "exposure_value", "exposure_unit", "denominator",
    "currency", "price_year", "exposure_basis", "exposure_kind", "confidence", "exposure_range",
    "derivation", "calculation", "statistic", "sample_size", "sample_note", "caveat", "status", "dispute_url", "withdrawn_reason",
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


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _log(root: Path, path: str) -> list[dict]:
    """Commits that touched `path`, oldest first: {commit, date, subject}."""
    out = _git(root, "log", "--follow", "--format=%H%x09%cs%x09%s", "--", path) or ""
    rows = [dict(zip(("commit", "date", "subject"), line.split("\t", 2))) for line in out.splitlines() if line]
    return rows[::-1]


def history(root: Path = ROOT) -> dict:
    """Where the record came from, recovered from git (the publish workflow checks out full history).

    schemas: every distinct document each schema has been, oldest first, with its x-schema-version
    ("unversioned" before versions were introduced) and the commit, so a reader can see what changed
    in each release. records: every commit that touched each source and publisher file. Empty
    outside a git checkout.
    """
    if _git(root, "rev-parse", "--is-inside-work-tree") is None:
        return {"schemas": {}, "records": {}}
    schemas = {}
    for name in SCHEMA_NAMES:
        # The pre-migration history lives at the old schema/<name>.schema.json path - git log
        # still has it even though the file itself moved to demitonapp/registers (spec 09 P4).
        rel = f"schema/{name}.schema.json"
        versions, last = [], None
        for c in _log(root, rel):
            text = _git(root, "show", f"{c['commit']}:{rel}")
            if text is None:
                continue
            doc = json.loads(text)
            if doc == last:
                continue
            last = doc
            versions.append({**c, "version": str(doc.get("x-schema-version") or "unversioned"), "document": doc})
        vendored = root / SCHEMA_DIR / f"{name}.schema.json"
        if vendored.exists():
            current = json.loads(vendored.read_text())
            if current != last:  # a version pinned from registers since the last history entry
                versions.append({"commit": None, "date": None, "subject": "pinned from demitonapp/registers",
                                 "version": str(current.get("x-schema-version") or "unversioned"), "document": current})
        schemas[name] = versions
    records = {}
    for d, pattern in (("sources", "*.md"), ("organisations", "*.yaml")):
        for p in sorted((root / d).glob(pattern)):
            records[f"{d}/{p.name}"] = _log(root, f"{d}/{p.name}")
    return {"schemas": schemas, "records": records}


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
    schemas = {p.name: json.loads(p.read_text()).get("x-schema-version") for p in sorted((ROOT / SCHEMA_DIR).glob("*.schema.json"))}
    _, sources, _, _ = load_corpus(ROOT)
    codes = {x for s in sources.values() for c in s["jurisdictions"] + s["industries"] for x in (c, c.split("-")[0])}
    vocab = {name: {k: v for k, v in json.loads((ROOT / "vocab" / f"{name}.json").read_text()).items() if k in codes}
             for name in ("jurisdictions", "industries")}
    vocab["subtypes"] = json.loads((ROOT / "vocab" / "subtypes.json").read_text())
    corpus = {
        "release": release, "schema_versions": schemas,
        "findings": [{**d, "path": r["_path"], "citations": r["_citations"]} for d, r in zip(data, full)],
        "sources": sources,
        # The body of each sources/<slug>.md: what the source says, in the contributor's own words.
        "source_notes": {p.stem: split_frontmatter(p.read_text())[1].strip() for p in sorted((ROOT / "sources").glob("*.md"))},
        "vocab": vocab,
        "schemas": {sp.name.split(".")[0]: json.loads(sp.read_text()) for sp in sorted((ROOT / SCHEMA_DIR).glob("*.schema.json"))},
        "history": history(ROOT),
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
