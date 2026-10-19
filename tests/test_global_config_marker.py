"""The marker file the project template reads to report that this configuration is present.

The template's specification (docs/specs/module-harness-files.md there) accepts a regular file of
at most 4 KiB that is a UTF-8 JSON object whose `schema` is the integer 1. This repository mirrors
the file like any other, so these checks read the tracked file and the manifest.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MARKER = "global-config.json"


class Marker(unittest.TestCase):
    def test_marker_is_listed_exactly_once_in_the_manifest(self):
        lines = (ROOT / "config-manifest.txt").read_text().splitlines()
        self.assertEqual(lines.count(MARKER), 1)

    def test_marker_is_a_small_regular_file(self):
        path = ROOT / MARKER
        self.assertTrue(path.is_file() and not path.is_symlink())
        self.assertLessEqual(path.stat().st_size, 4096)

    def test_marker_is_a_json_object_with_integer_schema_one(self):
        data = json.loads((ROOT / MARKER).read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertIs(type(data["schema"]), int)
        self.assertEqual(data["schema"], 1)

    def test_marker_carries_no_machine_state(self):
        self.assertEqual(set(json.loads((ROOT / MARKER).read_text())), {"schema"})


if __name__ == "__main__":
    unittest.main()
