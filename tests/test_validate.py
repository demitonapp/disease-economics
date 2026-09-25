"""The validator must fail on the things it claims to catch, not just pass on the corpus.

    python -m unittest discover -s tests
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from validate import check_against_base, validate  # noqa: E402

FINDING = "diseases/rework_signal/rework_total_civil_survey.yaml"


class CorpusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for d in ("schema", "vocab", "sources", "diseases", "context", "protections"):
            if (REPO / d).exists():
                shutil.copytree(REPO / d, self.tmp / d)
        (self.tmp / "protections").mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, rel, **changes):
        p = self.tmp / rel
        doc = yaml.safe_load(p.read_text())
        for k, v in changes.items():
            if v is None:
                doc.pop(k, None)
            else:
                doc[k] = v
        p.write_text(yaml.safe_dump(doc, sort_keys=False))

    def errors(self):
        return validate(self.tmp)[0]

    def assertFails(self, needle):
        errs = self.errors()
        self.assertTrue(any(needle in e for e in errs), f"expected an error containing {needle!r}, got {errs}")

    def test_corpus_passes(self):
        self.assertEqual(self.errors(), [])

    def test_a_subtype_must_belong_to_its_disease(self):
        self.edit(FINDING, subtype="payment")
        self.assertFails("not one of rework_signal's")
        self.edit(FINDING, subtype="workmanship")
        self.assertEqual(self.errors(), [])

    def test_a_context_figure_has_no_subtype(self):
        self.edit("context/planned_gross_margin.yaml", subtype="workmanship")
        self.assertFails("context/ figure has no subtype")

    def test_is_headline_is_gone(self):
        # Schema 2.0.0: no figure stands for a disease; which applies depends on where you work.
        self.edit(FINDING, is_headline=True)
        self.assertFails("is_headline")

    def test_none_unit_with_a_value_fails(self):
        self.edit(FINDING, exposure_unit="none")
        self.assertFails("go together")

    def test_ratio_of_other_needs_denominator(self):
        self.edit(FINDING, exposure_unit="ratio_of_other")
        self.assertFails("denominator")

    def test_per_unit_needs_price_year(self):
        self.edit("diseases/compliance_gate/noncompliance_cost_per_incident.yaml", price_year=None)
        self.assertFails("price_year")

    def test_missing_source_fails(self):
        self.edit(FINDING, sources=["no-such-source"])
        self.assertFails("does not exist")

    def test_uncited_source_fails(self):
        (self.tmp / "sources" / "orphan-2020-thing.md").write_text(
            (self.tmp / "sources" / "love-2010-rework-civil.md").read_text())
        self.assertFails("cited by no finding")

    def test_uk_is_rejected_with_a_hint(self):
        p = self.tmp / "sources" / "pye-tait-2017-retentions.md"
        p.write_text(p.read_text().replace("- GB", "- UK"))
        self.assertFails("GB")

    def test_global_must_stand_alone(self):
        p = self.tmp / "sources" / "hka-2025-crux.md"
        p.write_text(p.read_text().replace("- GLOBAL", "- GLOBAL\n- AU"))
        self.assertFails("only entry")

    def test_secondary_needs_read_via(self):
        # Any second-hand source will do; naming one breaks the day it is read at source.
        p = next(s for s in sorted((self.tmp / "sources").glob("*.md")) if "access: secondary" in s.read_text())
        text = p.read_text()
        start = text.index("read_via:")
        end = text.index("read_on:")
        p.write_text(text[:start] + text[end:])
        self.assertFails("read_via")


class BaseTest(CorpusTest):
    """The rules that compare a PR to its base branch."""

    def setUp(self):
        super().setUp()
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.tmp, check=True, capture_output=True)

    def base_errors(self):
        return check_against_base(self.tmp, "main")

    def test_unchanged_passes(self):
        self.assertEqual(self.base_errors(), [])

    def test_a_kind_reclassification_needs_history_not_a_source(self):
        self.edit(FINDING, exposure_kind="derived_contractor_loss")
        self.assertTrue(any("history entry" in e for e in self.base_errors()))
        self.edit(FINDING, history=[{"changed_on": "2026-10-01", "reason": "reclassified", "exposure_kind": "contractor_loss"}])
        self.assertEqual(self.base_errors(), [])

    def test_figure_change_needs_history_and_source(self):
        self.edit(FINDING, exposure_value=0.2)
        errs = self.base_errors()
        self.assertTrue(any("history entry" in e for e in errs), errs)
        self.assertTrue(any("sources/" in e for e in errs), errs)

    def test_figure_change_with_history_and_source_passes(self):
        self.edit(FINDING, exposure_value=0.2, history=[{
            "exposure_value": 0.1, "changed_on": "2026-10-01", "reason": "new survey"}])
        p = self.tmp / "sources" / "love-2010-rework-civil.md"
        p.write_text(p.read_text() + "\nA newer reading.\n")
        self.assertEqual(self.base_errors(), [])

    def test_deleting_a_finding_fails(self):
        (self.tmp / FINDING).unlink()
        self.assertTrue(any("never deleted" in e for e in self.base_errors()))

    def test_history_is_append_only(self):
        self.edit(FINDING, history=[{"changed_on": "2026-10-01", "reason": "a"}])
        self.git("add", ".")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "with history")
        self.edit(FINDING, history=[{"changed_on": "2026-10-01", "reason": "rewritten"}])
        self.assertTrue(any("append-only" in e for e in self.base_errors()))

    def _bumped(self, part):
        """The finding schema's current version with one part bumped: tests follow the schema's own history."""
        import json
        major, minor, patch = map(int, json.loads((self.tmp / "schema" / "finding.schema.json").read_text())["x-schema-version"].split("."))
        return {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[part]

    def _schema(self, change, version):
        import json
        sp = self.tmp / "schema" / "finding.schema.json"
        s = json.loads(sp.read_text())
        change(s)
        if version:
            s["x-schema-version"] = version
        sp.write_text(json.dumps(s, indent=2))

    def test_widening_an_enum_needs_a_minor_bump(self):
        widen = lambda s: s["properties"]["denominator"]["enum"].append("new_denominator")  # noqa: E731
        minor = self._bumped("minor")
        self._schema(widen, None)
        self.assertTrue(any("MINOR" in e for e in self.base_errors()))
        self._schema(lambda s: None, minor)
        self.assertEqual(self.base_errors(), [])

    def test_narrowing_an_enum_needs_a_major_bump(self):
        narrow = lambda s: s["properties"]["confidence"]["enum"].remove("low")  # noqa: E731
        minor, major = self._bumped("minor"), self._bumped("major")
        self._schema(narrow, minor)
        self.assertTrue(any("MAJOR" in e for e in self.base_errors()))
        self._schema(lambda s: None, major)
        self.assertEqual(self.base_errors(), [])

    def test_a_description_change_needs_a_patch_bump(self):
        patch = self._bumped("patch")
        self._schema(lambda s: s.update(description="reworded"), None)
        self.assertTrue(any("PATCH" in e for e in self.base_errors()))
        self._schema(lambda s: None, patch)
        self.assertEqual(self.base_errors(), [])

    def test_typo_fix_needs_no_source(self):
        self.edit(FINDING, caveat="Respondents' estimates, not measured cost records.")
        self.assertEqual(self.base_errors(), [])


if __name__ == "__main__":
    unittest.main()
