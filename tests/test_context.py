"""Tests for the plan fields reported by `claude-workflow context`.

Run from the repository root with:  python3 -B -m unittest discover -s tests
Set TOOLS_BIN to test another copy of the tools. Uses throwaway repositories.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BIN = Path(os.environ.get("TOOLS_BIN", Path(__file__).resolve().parents[1] / "bin"))


class ContextPlanFields(unittest.TestCase):
    def context(self, plan_text):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "base"], cwd=root, env=env, check=True)
            if plan_text is not None:
                (root / "docs" / "plans").mkdir(parents=True)
                (root / "docs" / "plans" / "next.md").write_text(plan_text)
            out = subprocess.run([sys.executable, "-B", str(BIN / "claude-workflow"), "context"],
                                 cwd=root, capture_output=True, text=True, check=True).stdout
            return json.loads(out)

    def test_status_line_is_reported_for_a_template_style_plan(self):
        for status in ("Empty — no active plan", "Proposed", "Approved", "In Progress"):
            with self.subTest(status=status):
                ctx = self.context("# Next plan\n\nStatus: %s\nCreated: 2026-01-01\n\n### Increment A — x\n" % status)
                self.assertEqual(ctx["next_plan_status"], status)
                self.assertIsNone(ctx["next_plan_has_unfinished"])

    def test_checkbox_plans_still_report_unfinished_items(self):
        ctx = self.context("# Plan\n- [x] done\n- [ ] todo\n")
        self.assertTrue(ctx["next_plan_has_unfinished"])
        self.assertIsNone(ctx["next_plan_status"])

    def test_missing_plan_reports_nothing(self):
        ctx = self.context(None)
        self.assertIsNone(ctx["next_plan"])
        self.assertIsNone(ctx["next_plan_status"])


if __name__ == "__main__":
    unittest.main()
