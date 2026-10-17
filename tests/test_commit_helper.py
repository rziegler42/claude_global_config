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


class CommitFixture(unittest.TestCase):
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


class CommitHelper(CommitFixture):
    def test_subject_only_still_works(self):
        r = self.commit("--subject", "Update a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.message(), "Update a")

    def test_body_and_trailers_are_recorded_exactly(self):
        r = self.commit("--subject", "Update a", "--body", "First line.\nSecond line.",
                        "--trailer", "Co-Authored-By: Pat <pat@example.com>",
                        "--trailer", "Reviewed-by: Someone <s@example.com>")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.message(), "Update a\n\nFirst line.\nSecond line.\n\n"
                         "Co-Authored-By: Pat <pat@example.com>\n"
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


class RepositoryPrograms(CommitFixture):
    """A repository that selects a program for the commit to run is refused unless the owner opts in.

    The Codex approver may allow a commit with no dialog, so the helper must not run repository-chosen code
    that the approver's own gate would have declined, even if the repository changed after approval.
    """

    def setUp(self):
        super().setUp()
        marks = tempfile.TemporaryDirectory()
        self.addCleanup(marks.cleanup)
        self.mark = Path(marks.name).resolve() / "ran"

    def add_hook(self, name="pre-commit"):
        hook = self.root / ".git" / "hooks" / name
        hook.write_text("#!/bin/sh\necho %s > '%s'\nexit 0\n" % (name, self.mark))
        hook.chmod(0o755)

    def assert_refused(self, *extra):
        head = self.git("rev-parse", "HEAD")
        r = self.commit("--subject", "Update a", *extra)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("repository", (r.stderr + r.stdout).lower())
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertFalse(self.mark.exists(), "repository code ran")

    def test_executable_hook_is_refused_and_does_not_run(self):
        self.add_hook()
        self.assert_refused()

    def test_every_exec_config_shape_is_refused(self):
        for key, value in (("core.hooksPath", "elsewhere"), ("filter.x.clean", "cat"), ("filter.x.process", "cat"),
                           ("commit.gpgsign", "true"), ("gpg.program", "gpg"), ("gpg.ssh.defaultKeyCommand", "x"),
                           ("diff.x.textconv", "cat"), ("core.fsmonitor", "x"), ("core.sshCommand", "ssh")):
            with self.subTest(key=key):
                self.git("config", key, value)
                self.assert_refused()
                self.git("config", "--unset", key)

    def test_a_sample_hook_and_a_non_executable_hook_are_not_findings(self):
        sample = self.root / ".git" / "hooks" / "pre-commit.sample"
        sample.write_text("#!/bin/sh\nexit 1\n")
        sample.chmod(0o755)
        (self.root / ".git" / "hooks" / "commit-msg").write_text("#!/bin/sh\nexit 1\n")
        r = self.commit("--subject", "Update a")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_hook_added_after_approval_is_still_refused(self):
        # The approver judged the repository clean; the helper checks again when it actually runs.
        head = self.git("rev-parse", "HEAD")
        self.add_hook()
        r = self.helper("commit", "--expected-head", head, "--subject", "Update a", "--", "a.txt")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.mark.exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_a_head_that_moved_after_approval_is_refused(self):
        stale = self.git("rev-parse", "HEAD")
        (self.root / "b.txt").write_text("b2\n")
        self.git("add", "b.txt")
        self.git("commit", "-q", "-m", "intervening")
        moved = self.git("rev-parse", "HEAD")
        r = self.helper("commit", "--expected-head", stale, "--subject", "Update a", "--", "a.txt")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("HEAD changed", r.stdout + r.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), moved)

    def test_work_staged_after_approval_is_refused_not_swept_in(self):
        head = self.git("rev-parse", "HEAD")
        (self.root / "b.txt").write_text("b2\n")
        self.git("add", "b.txt")
        r = self.helper("commit", "--expected-head", head, "--subject", "Update a", "--", "a.txt")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "b.txt")

    def test_the_owner_can_opt_in_and_the_hook_then_runs(self):
        self.add_hook()
        r = self.commit("--subject", "Update a", "--allow-repo-programs")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.mark.exists())
        self.assertEqual(self.message(), "Update a")

    def test_git_runs_with_replace_refs_ignored(self):
        bin_dir = Path(self.tmp.name).parent / ("wrap-" + self.root.name)
        bin_dir.mkdir()
        self.addCleanup(lambda: [p.unlink() for p in bin_dir.iterdir()] or bin_dir.rmdir())
        seen = bin_dir / "seen"
        real = subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()
        wrapper = bin_dir / "git"
        wrapper.write_text("#!/bin/sh\necho \"$GIT_NO_REPLACE_OBJECTS\" >> '%s'\nexec %s \"$@\"\n" % (seen, real))
        wrapper.chmod(0o755)
        env = {**ENV, "PATH": "%s:%s" % (bin_dir, os.environ["PATH"])}
        r = subprocess.run([sys.executable, "-B", str(BIN / "claude-workflow"), "commit", "--expected-head",
                            self.git("rev-parse", "HEAD"), "--subject", "Update a", "--", "a.txt"],
                           cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        values = seen.read_text().split()
        self.assertTrue(values and set(values) == {"1"}, values)


if __name__ == "__main__":
    unittest.main()
