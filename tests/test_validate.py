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

HEADLINE = "diseases/rework_signal/rework_total_civil_survey.yaml"


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

    def test_owner_side_cannot_be_headline(self):
        self.edit(HEADLINE, exposure_kind="owner_side")
        self.assertFails("a headline must be")

    def test_two_headlines_fail(self):
        self.edit("diseases/rework_signal/rework_split_direct_indirect.yaml", is_headline=True)
        self.assertFails("needs exactly one is_headline")

    def test_none_unit_with_a_value_fails(self):
        self.edit(HEADLINE, exposure_unit="none")
        self.assertFails("go together")

    def test_ratio_of_other_needs_denominator(self):
        self.edit(HEADLINE, exposure_unit="ratio_of_other")
        self.assertFails("denominator")

    def test_per_unit_needs_price_year(self):
        self.edit("diseases/compliance_gate/noncompliance_cost_per_incident.yaml", price_year=None)
        self.assertFails("price_year")

    def test_missing_source_fails(self):
        self.edit(HEADLINE, sources=["no-such-source"])
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

    def test_context_cannot_be_headline(self):
        self.edit("context/planned_gross_margin.yaml", is_headline=True)
        self.assertFails("never a headline")


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

    def test_figure_change_needs_history_and_source(self):
        self.edit(HEADLINE, exposure_value=0.2)
        errs = self.base_errors()
        self.assertTrue(any("history entry" in e for e in errs), errs)
        self.assertTrue(any("sources/" in e for e in errs), errs)

    def test_figure_change_with_history_and_source_passes(self):
        self.edit(HEADLINE, exposure_value=0.2, history=[{
            "exposure_value": 0.1, "changed_on": "2026-10-01", "reason": "new survey"}])
        p = self.tmp / "sources" / "love-2010-rework-civil.md"
        p.write_text(p.read_text() + "\nA newer reading.\n")
        self.assertEqual(self.base_errors(), [])

    def test_deleting_a_finding_fails(self):
        (self.tmp / HEADLINE).unlink()
        self.assertTrue(any("never deleted" in e for e in self.base_errors()))

    def test_history_is_append_only(self):
        self.edit(HEADLINE, history=[{"changed_on": "2026-10-01", "reason": "a"}])
        self.git("add", ".")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "with history")
        self.edit(HEADLINE, history=[{"changed_on": "2026-10-01", "reason": "rewritten"}])
        self.assertTrue(any("append-only" in e for e in self.base_errors()))

    def test_typo_fix_needs_no_source(self):
        self.edit(HEADLINE, caveat="Respondents' estimates, not measured cost records.")
        self.assertEqual(self.base_errors(), [])


if __name__ == "__main__":
    unittest.main()
