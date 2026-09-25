"""Validate the corpus. Every rule here is written down in METHOD.md or CONTRIBUTING.md.

    python scripts/validate.py                  # the corpus as it stands
    python scripts/validate.py --base origin/main   # plus the rules that compare a PR to its base

Exit code 1 on any error. Warnings print but do not fail.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
DISEASE_KEYS = ("rework_signal", "overrun_signal", "claim_window", "evidence_gap", "compliance_gate")
SOLE_ENTRIES = ("GLOBAL", "ALL", "unknown")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
METRIC_KEY = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
#: A change to any of these is a change to the figure: it needs evidence and a history entry.
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
FIGURE_FIELDS = ("exposure_value", "exposure_unit", "denominator", "exposure_range", "exposure_kind", "confidence")


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps dates as strings, so `read_on: 2026-09-14` validates as a string."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(text: str):
    return yaml.load(text, Loader=_Loader)


def split_frontmatter(text: str):
    """(frontmatter dict, body) of a sources/*.md file, or (None, text) if it has none."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    return load_yaml(text[4:end]), text[end + 5:]


def _validators(root: Path):
    schemas = {p.name: json.loads(p.read_text()) for p in (root / "schema").glob("*.schema.json")}
    registry = Registry().with_resources(
        (name, Resource.from_contents(s)) for name, s in schemas.items()
    ).with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    return {name.split(".")[0]: Draft202012Validator(s, registry=registry) for name, s in schemas.items()}


def _citation_slug(c) -> str:
    return c if isinstance(c, str) else c["source"]


def load_corpus(root: Path):
    """Every source, finding and protection, keyed by repo-relative path. Parse errors are returned, not raised."""
    errors, sources, findings, protections = [], {}, {}, {}
    for p in sorted((root / "sources").glob("*.md")):
        fm, _ = split_frontmatter(p.read_text())
        if fm is None:
            errors.append(f"{p.relative_to(root)}: no YAML frontmatter")
            continue
        sources[p.stem] = fm
    for p in sorted(list((root / "diseases").glob("*/*.yaml")) + list((root / "context").glob("*.yaml"))):
        findings[str(p.relative_to(root))] = load_yaml(p.read_text())
    for p in sorted((root / "protections").glob("*/*.yaml")):
        protections[str(p.relative_to(root))] = load_yaml(p.read_text())
    return errors, sources, findings, protections


def validate(root: Path = ROOT):
    """(errors, warnings) for the corpus at `root`."""
    errors, sources, findings, protections = load_corpus(root)
    warnings: list[str] = []
    v = _validators(root)
    jurisdictions = json.loads((root / "vocab" / "jurisdictions.json").read_text())
    industries = json.loads((root / "vocab" / "industries.json").read_text())
    gates = json.loads((root / "vocab" / "gates.json").read_text())
    subtypes = {k: {st["key"] for st in v} for k, v in json.loads((root / "vocab" / "subtypes.json").read_text()).items()}

    def schema_errors(path, doc, validator):
        for e in sorted(validator.iter_errors(doc), key=str):
            where = "/".join(map(str, e.absolute_path)) or "(file)"
            errors.append(f"{path}: {where}: {e.message}")

    # ---- schema versions -------------------------------------------------
    for sp in sorted((root / "schema").glob("*.schema.json")):
        ver = json.loads(sp.read_text()).get("x-schema-version", "")
        if not SEMVER.match(str(ver)):
            errors.append(f"schema/{sp.name}: x-schema-version must be MAJOR.MINOR.PATCH, got {ver!r}")

    # ---- sources -------------------------------------------------------
    for slug, fm in sources.items():
        path = f"sources/{slug}.md"
        if not SLUG.match(slug):
            errors.append(f"{path}: filename must be lower-case words joined by hyphens")
        schema_errors(path, fm, v["source"])
        for field, vocab in (("jurisdictions", jurisdictions), ("industries", industries)):
            values = fm.get(field) or []
            for value in values:
                if value not in vocab:
                    hint = " (the UK's ISO code is GB)" if value == "UK" else ""
                    errors.append(f"{path}: {field}: {value!r} is not in vocab/{field}.json{hint}")
            for sole in SOLE_ENTRIES:
                if sole in values and len(values) > 1:
                    errors.append(f"{path}: {field}: {sole!r} must be the only entry")

    # ---- findings ------------------------------------------------------
    for path, f in findings.items():
        parts = Path(path).parts
        is_context = parts[0] == "context"
        if not METRIC_KEY.match(Path(path).stem):
            errors.append(f"{path}: filename (the metric_key) must be lower-case words joined by underscores")
        if not is_context and parts[1] not in DISEASE_KEYS:
            errors.append(f"{path}: {parts[1]!r} is not one of the five disease keys {DISEASE_KEYS}")
            continue
        if not isinstance(f, dict):
            errors.append(f"{path}: not a YAML mapping")
            continue
        schema_errors(path, f, v["finding"])
        value, unit, kind = f.get("exposure_value"), f.get("exposure_unit"), f.get("exposure_kind")
        if (unit == "none") != (value is None):
            errors.append(f"{path}: exposure_unit 'none' and exposure_value null go together (none means no figure exists)")
        if unit in ("ratio_of_contract", "ratio_of_other") and value is not None and value <= 0:
            errors.append(f"{path}: a ratio must be above 0")
        if unit == "ratio_of_contract" and value is not None and value > 1:
            warnings.append(f"{path}: ratio_of_contract above 1 - fine for an overrun, a unit error for a share")
        rng = f.get("exposure_range")
        if rng and value is not None and not (rng["low"] <= value <= rng["high"]):
            errors.append(f"{path}: exposure_range must satisfy low <= exposure_value <= high")
        st = f.get("subtype")
        if st and is_context:
            errors.append(f"{path}: a context/ figure has no subtype")
        elif st and st not in subtypes.get(parts[1], set()):
            errors.append(f"{path}: subtype {st!r} is not one of {parts[1]}'s in vocab/subtypes.json")
        if is_context:
            if kind != "context":
                errors.append(f"{path}: a context/ file has exposure_kind 'context'")
        elif kind == "context":
            errors.append(f"{path}: exposure_kind 'context' belongs in context/, not diseases/")

    # ---- protections ---------------------------------------------------
    for path, pr in protections.items():
        parts = Path(path).parts
        if parts[1] not in gates:
            errors.append(f"{path}: {parts[1]!r} has no mechanisms in vocab/gates.json")
        elif Path(path).stem not in gates[parts[1]]:
            errors.append(f"{path}: {Path(path).stem!r} is not a mechanism of {parts[1]} in vocab/gates.json")
        if isinstance(pr, dict):
            schema_errors(path, pr, v["protection"])

    # ---- citations -----------------------------------------------------
    cited: set[str] = set()
    for path, doc in {**findings, **protections}.items():
        if not isinstance(doc, dict):
            continue
        refs = [_citation_slug(c) for c in doc.get("sources") or []]
        refs += [c["source"] for c in doc.get("considered") or [] if isinstance(c, dict) and "source" in c]
        for slug in refs:
            cited.add(slug)
            if slug not in sources:
                errors.append(f"{path}: cites {slug!r}, but sources/{slug}.md does not exist")
    for slug in sorted(set(sources) - cited):
        errors.append(f"sources/{slug}.md: cited by no finding or protection (an unused source is an unreviewed claim)")

    # ---- organisation spellings (warn only) -----------------------------
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("&", " and ")).split()

    orgs = sorted({fm.get("organisation", "") for fm in sources.values() if isinstance(fm, dict)})
    for i, a in enumerate(orgs):
        for b in orgs[i + 1:]:
            na, nb = " ".join(norm(a)), " ".join(norm(b))
            if na != nb and difflib.SequenceMatcher(None, na, nb).ratio() > 0.92:
                warnings.append(f"organisation spellings may be the same body: {a!r} / {b!r}")

    return errors, warnings


def _schema_facts(schema) -> dict:
    """The parts of a JSON Schema a version bump is judged on, keyed by JSON pointer."""
    facts = {"props": {}, "required": {}, "enum": {}, "type": {}}

    def walk(node, ptr):
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                facts["props"][ptr] = set(node["properties"])
            if isinstance(node.get("required"), list):
                facts["required"][ptr] = set(node["required"])
            if "enum" in node:
                facts["enum"][ptr] = {json.dumps(v) for v in node["enum"]}
            if "type" in node:
                facts["type"][ptr] = json.dumps(node["type"], sort_keys=True)
            for k, v in node.items():
                if k != "x-schema-version":
                    walk(v, f"{ptr}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{ptr}/{i}")

    walk(schema, "#")
    return facts


def schema_bump_needed(old: dict, new: dict):
    """None if unchanged; else 'major', 'minor' or 'patch', the same rule the monorepo's shelf contracts use.

    MAJOR: a property removed, a new requirement, an enum narrowed, a type changed.
    MINOR: a property added, an enum widened. PATCH: anything else (descriptions, patterns, examples).
    """
    strip = lambda s: {k: v for k, v in s.items() if k != "x-schema-version"}  # noqa: E731
    if strip(old) == strip(new):
        return None
    a, b = _schema_facts(old), _schema_facts(new)
    if (any(p not in b["props"] or not a["props"][p] <= b["props"][p] for p in a["props"])
            or any(not b["required"][p] <= a["required"].get(p, set()) for p in b["required"])
            or any(p in b["enum"] and not a["enum"][p] <= b["enum"][p] for p in a["enum"])
            or any(p in b["type"] and a["type"][p] != b["type"][p] for p in a["type"])):
        return "major"
    if (any(b["props"][p] - a["props"].get(p, set()) for p in b["props"])
            or any(b["enum"][p] - a["enum"].get(p, set()) for p in b["enum"])):
        return "minor"
    return "patch"


def _bumped_enough(old_v: str, new_v: str, level: str) -> bool:
    o, n = tuple(map(int, SEMVER.match(old_v).groups())), tuple(map(int, SEMVER.match(new_v).groups()))
    if level == "major":
        return n[0] > o[0]
    if level == "minor":
        return n[0] > o[0] or (n[0] == o[0] and n[1] > o[1])
    return n > o


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def check_against_base(root: Path, base: str):
    """The rules that need the PR's base: no deletions, history append-only, figure changes carry evidence."""
    errors = []
    base_files = [p for p in _git(root, "ls-tree", "-r", "--name-only", base).splitlines()
                  if (p.startswith("diseases/") or p.startswith("context/")) and p.endswith(".yaml")]
    changed = set(_git(root, "diff", "--name-only", base, "--", "sources/").splitlines())
    changed |= set(_git(root, "ls-files", "--others", "--exclude-standard", "sources/").splitlines())
    for sp in [p for p in _git(root, "ls-tree", "-r", "--name-only", base).splitlines()
               if p.startswith("schema/") and p.endswith(".schema.json")]:
        if not (root / sp).exists():
            errors.append(f"{sp}: a schema is never deleted")
            continue
        old, new = json.loads(_git(root, "show", f"{base}:{sp}")), json.loads((root / sp).read_text())
        level = schema_bump_needed(old, new)
        ov, nv = str(old.get("x-schema-version", "0.0.0")), str(new.get("x-schema-version", ""))
        if level and SEMVER.match(ov) and SEMVER.match(nv) and not _bumped_enough(ov, nv, level):
            errors.append(f"{sp}: this is a {level.upper()} change - bump x-schema-version from {ov} accordingly (now {nv})")
    for path in base_files:
        if not (root / path).exists():
            errors.append(f"{path}: a finding is never deleted - set status: withdrawn with a withdrawn_reason")
            continue
        old = load_yaml(_git(root, "show", f"{base}:{path}")) or {}
        new = load_yaml((root / path).read_text()) or {}
        old_h, new_h = old.get("history") or [], new.get("history") or []
        if new_h[: len(old_h)] != old_h:
            errors.append(f"{path}: history is append-only - an existing entry was changed or removed")
        moved = [k for k in FIGURE_FIELDS if old.get(k) != new.get(k)]
        if moved:
            if len(new_h) <= len(old_h):
                errors.append(f"{path}: {moved} changed - append a history entry recording the old figure and why")
            # Reclassifying a figure's kind under the method is not a new reading of the evidence, so it
            # needs its history entry but no new source (METHOD.md Section 8).
            if not changed and moved != ["exposure_kind"]:
                errors.append(f"{path}: {moved} changed - the same PR must add or change a file under sources/")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="git ref of the PR's base branch, e.g. origin/main")
    args = ap.parse_args()
    errors, warnings = validate(ROOT)
    if args.base:
        errors += check_against_base(ROOT, args.base)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
