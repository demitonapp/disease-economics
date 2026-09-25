"""The site renders every finding in the corpus, and nothing it cannot say.

    python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_ledger import rows  # noqa: E402
from build_site import figure, render  # noqa: E402
from validate import ROOT  # noqa: E402


class SiteTest(unittest.TestCase):
    def test_every_finding_is_on_the_page(self):
        html = render("test", "2026-01-01")
        for r in rows(ROOT):
            self.assertIn(f'id="{r["id"]}"', html, r["id"])
        self.assertNotIn(">None<", html)

    def test_figures_read_as_their_unit(self):
        self.assertEqual(figure({"exposure_unit": "ratio_of_contract", "exposure_value": 0.0025}), ("0.25%", "of contract value"))
        self.assertEqual(figure({"exposure_unit": "ratio_of_other", "exposure_value": 0.83, "denominator": "arbitration_cost"})[1],
                         "of total arbitration costs")
        self.assertEqual(figure({"exposure_unit": "per_incident", "exposure_value": 60100000.0, "currency": "USD", "price_year": 2024})[0], "US$60.1m")
        self.assertEqual(figure({"exposure_unit": "none", "exposure_value": None})[0], "No figure")


if __name__ == "__main__":
    unittest.main()
