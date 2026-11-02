"""The SM070 grid: for each of the registers' 25 causes, in Australia and in New Zealand at national level,
does the corpus hold a figure, or a recorded 'none'?

    python scripts/grid.py                      # all 50 cells, exit 1 if any is empty
    python scripts/grid.py --report             # same table, always exit 0
    python scripts/grid.py --disease disputes --country NZ     # just those cells

A cell is the cause (a finding's `subtype`) in a country (a code in the finding's `jurisdictions`, which are
the union of its sources'). A state-only figure (`AU-QLD`) does not fill the national `AU` cell (SM070 decision 7),
and nor does GLOBAL or another country's.

  figure  a live finding with a value for that cause and country
  none    a live `exposure_unit: none` finding for that cause and country that names at least NONE_MIN
          sources in `considered` (SM070 decision 6): "we looked, and here is where"
  thin    a `none` record with fewer than NONE_MIN considered: not yet a record of a search
  empty   nothing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ledger import rows  # noqa: E402
from validate import ROOT, disease_vocab  # noqa: E402

COUNTRIES = ("AU", "NZ")
NONE_MIN = 8


def state(findings: list[dict], disease: str, cause: str, country: str) -> tuple[str, list[str]]:
    mine = [r for r in findings if r["disease_key"] == disease and r.get("subtype") == cause
            and country in r["jurisdictions"] and r.get("status") != "withdrawn"]
    figures = [r for r in mine if r["exposure_unit"] != "none"]
    if figures:
        return "figure", [r["id"] for r in figures]
    nones = [r for r in mine if r["exposure_unit"] == "none"]
    if any(len(r.get("considered") or []) >= NONE_MIN for r in nones):
        return "none", [r["id"] for r in nones]
    return ("thin" if nones else "empty"), [r["id"] for r in nones]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="print the grid and exit 0 even with empty cells")
    ap.add_argument("--disease")
    ap.add_argument("--country", choices=COUNTRIES)
    args = ap.parse_args()
    findings = rows(ROOT)
    vocab = disease_vocab(ROOT)
    if args.disease and args.disease not in vocab:
        print(f"unknown disease {args.disease!r}; one of {list(vocab)}", file=sys.stderr)
        return 2
    open_cells, total = 0, 0
    for disease, causes in vocab.items():
        if args.disease and disease != args.disease:
            continue
        print(f"\n{disease}")
        for cause in causes:
            parts = []
            for country in COUNTRIES:
                if args.country and country != args.country:
                    continue
                st, ids = state(findings, disease, cause, country)
                total += 1
                open_cells += st in ("empty", "thin")
                parts.append(f"{country} {st}{f' ({len(ids)})' if ids else ''}")
            print(f"  {cause:28s} " + "   ".join(parts))
    print(f"\n{total - open_cells} of {total} cells filled, {open_cells} open")
    return 0 if args.report or not open_cells else 1


if __name__ == "__main__":
    sys.exit(main())
