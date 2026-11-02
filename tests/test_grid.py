"""The SM070 grid decides when a cell is filled: these are its rules."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from grid import NONE_MIN, state  # noqa: E402


def row(**kw):
    base = dict(id="disputes/x", disease_key="disputes", subtype="payment_dispute", jurisdictions=["AU"],
                exposure_unit="ratio_of_other", status="current", considered=None)
    return {**base, **kw}


class GridTest(unittest.TestCase):
    def test_a_national_figure_fills_its_cell(self):
        self.assertEqual(state([row()], "disputes", "payment_dispute", "AU")[0], "figure")

    def test_a_state_only_figure_does_not_fill_the_national_cell(self):
        self.assertEqual(state([row(jurisdictions=["AU-QLD"])], "disputes", "payment_dispute", "AU")[0], "empty")

    def test_another_country_or_global_does_not_fill_it(self):
        for j in (["NZ"], ["GLOBAL"], ["GB"]):
            self.assertEqual(state([row(jurisdictions=j)], "disputes", "payment_dispute", "AU")[0], "empty")

    def test_a_withdrawn_figure_does_not_count(self):
        self.assertEqual(state([row(status="withdrawn")], "disputes", "payment_dispute", "AU")[0], "empty")

    def test_another_cause_or_disease_does_not_count(self):
        self.assertEqual(state([row(subtype="delay_dispute")], "disputes", "payment_dispute", "AU")[0], "empty")
        self.assertEqual(state([row(disease_key="rework")], "disputes", "payment_dispute", "AU")[0], "empty")

    def test_a_none_record_needs_eight_considered_sources(self):
        few = row(exposure_unit="none", considered=[{"source": f"s{i}", "reason": "r"} for i in range(NONE_MIN - 1)])
        enough = row(exposure_unit="none", considered=[{"source": f"s{i}", "reason": "r"} for i in range(NONE_MIN)])
        self.assertEqual(state([few], "disputes", "payment_dispute", "AU")[0], "thin")
        self.assertEqual(state([enough], "disputes", "payment_dispute", "AU")[0], "none")

    def test_a_figure_wins_over_a_none_record(self):
        none = row(id="a", exposure_unit="none", considered=[{"source": f"s{i}", "reason": "r"} for i in range(NONE_MIN)])
        self.assertEqual(state([none, row(id="b")], "disputes", "payment_dispute", "AU")[0], "figure")


if __name__ == "__main__":
    unittest.main()
