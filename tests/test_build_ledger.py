"""corpus.json carries where the record came from: every schema version and every record's commits."""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from build_ledger import history  # noqa: E402


class HistoryTest(unittest.TestCase):
    def test_every_schema_ends_at_its_current_version(self):
        h = history(REPO)
        if not h["schemas"]:
            self.skipTest("not a git checkout")
        for sp in (REPO / "schema").glob("*.schema.json"):
            versions = h["schemas"][sp.name.split(".")[0]]
            self.assertTrue(versions, sp.name)
            self.assertEqual(versions[-1]["document"], json.loads(sp.read_text()), sp.name)
            self.assertEqual(versions[-1]["version"], json.loads(sp.read_text()).get("x-schema-version", "unversioned"))

    def test_every_source_has_a_record_history(self):
        h = history(REPO)
        if not h["records"]:
            self.skipTest("not a git checkout")
        for p in (REPO / "sources").glob("*.md"):
            self.assertTrue(h["records"][f"sources/{p.name}"], p.name)


if __name__ == "__main__":
    unittest.main()
