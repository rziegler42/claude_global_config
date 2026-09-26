"""Tests for `claude-workflow commit` / `amend-message` message and staged-work handling.

Run from the repository root with:  python3 -B -m unittest discover -s tests
Set TOOLS_BIN to test another copy of the tools.

Every test uses a throwaway repository under a temporary directory.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BIN = Path(os.environ.get("TOOLS_BIN", Path(__file__).resolve().parents[1] / "bin"))
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


class CommitHelper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.git("init", "-q", "-b", "main")
        (self.root / "a.txt").write_text("a\n")
        (self.root / "b.txt").write_text("b\n")
        self.git("add", "a.txt", "b.txt")
        self.git("commit", "-q", "-m", "base")
        (self.root / "a.txt").write_text("a2\n")

    def git(self, *args):
        r = subprocess.run(["git", *args], cwd=self.root, env=ENV, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def helper(self, sub, *args):
        return subprocess.run([sys.executable, "-B", str(BIN / "claude-workflow"), sub, *args],
                              cwd=self.root, env=ENV, capture_output=True, text=True)

    def commit(self, *args, paths=("a.txt",)):
        return self.helper("commit", "--expected-head", self.git("rev-parse", "HEAD"), *args, "--", *paths)

    def message(self):
        return self.git("show", "-s", "--format=%B", "HEAD")

    def test_subject_only_still_works(self):
        r = self.commit("--subject", "Update a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.message(), "Update a")

    def test_body_and_trailers_are_recorded_exactly(self):
        r = self.commit("--subject", "Update a", "--body", "First line.\nSecond line.",
                        "--trailer", "Co-Authored-By: Claude <noreply@example.com>",
                        "--trailer", "Reviewed-by: Someone <s@example.com>")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.message(), "Update a\n\nFirst line.\nSecond line.\n\n"
                         "Co-Authored-By: Claude <noreply@example.com>\n"
                         "Reviewed-by: Someone <s@example.com>")
        self.assertEqual(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), "a.txt")

    def test_body_starting_with_dash_or_hash_is_data(self):
        r = self.commit("--subject", "Update a", "--body", "-x is a flag\n# not a comment")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.message(), "Update a\n\n-x is a flag\n# not a comment")

    def test_bad_message_parts_are_rejected_without_committing(self):
        head = self.git("rev-parse", "HEAD")
        for extra in (["--trailer", "no colon"], ["--trailer", "Key: a\nOther: b"],
                      ["--trailer", "Bad Key: v"], ["--trailer", "Key:"],
                      ["--body", "   "], ["--body", "a\rb"]):
            with self.subTest(extra=extra):
                r = self.commit("--subject", "Update a", *extra)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(self.git("rev-parse", "HEAD"), head)
                self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_default_refuses_when_anything_is_staged(self):
        (self.root / "b.txt").write_text("b2\n")
        self.git("add", "b.txt")
        head = self.git("rev-parse", "HEAD")
        r = self.commit("--subject", "Update a")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--leave-other-staged", r.stderr + r.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "b.txt")

    def test_leave_other_staged_commits_only_the_exact_paths(self):
        (self.root / "b.txt").write_text("b2\n")
        self.git("add", "b.txt")
        (self.root / "b.txt").write_text("b3\n")  # unstaged edit on top of staged work
        r = self.commit("--subject", "Update a", "--body", "Only a.", "--leave-other-staged")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), "a.txt")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "b.txt")
        self.assertEqual(self.git("show", ":b.txt"), "b2")
        self.assertEqual((self.root / "b.txt").read_text(), "b3\n")
        self.assertIn('"left_staged": ["b.txt"]', r.stdout)

    def test_leave_other_staged_handles_a_new_file(self):
        (self.root / "new.txt").write_text("n\n")
        (self.root / "b.txt").write_text("b2\n")
        self.git("add", "b.txt")
        r = self.commit("--subject", "Add new", "--leave-other-staged", paths=("new.txt",))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), "new.txt")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "b.txt")

    def test_leave_other_staged_refuses_when_an_eligible_path_is_already_staged(self):
        self.git("add", "a.txt")
        (self.root / "b.txt").write_text("b2\n")
        self.git("add", "b.txt")
        head = self.git("rev-parse", "HEAD")
        r = self.commit("--subject", "Update a", "--leave-other-staged")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("diff", "--cached", "--name-only").split(), ["a.txt", "b.txt"])

    def test_failed_check_restores_only_the_eligible_paths(self):
        (self.root / "a.txt").write_text("trailing space \n")
        (self.root / "b.txt").write_text("b2\n")
        self.git("add", "b.txt")
        head = self.git("rev-parse", "HEAD")
        r = self.commit("--subject", "Update a", "--leave-other-staged")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "b.txt")

    def test_amend_message_accepts_body_and_trailers(self):
        (self.root / "a.txt").write_text("a\n")
        head = self.git("rev-parse", "HEAD")
        r = self.helper("amend-message", "--expected-head", head, "--subject", "New subject",
                        "--body", "Why.", "--trailer", "Co-Authored-By: C <c@example.com>")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.message(), "New subject\n\nWhy.\n\nCo-Authored-By: C <c@example.com>")
        r = self.helper("amend-message", "--expected-head", self.git("rev-parse", "HEAD"),
                        "--subject", "S", "--trailer", "bad")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
