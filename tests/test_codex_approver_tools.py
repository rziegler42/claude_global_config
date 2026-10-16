"""Tests for the multi-tool engine of hooks/codex_approver.py (plan: docs/plans/next.md, increment B).

Run from the repository root with:  python3 -B -m unittest discover -s tests

The engine matches `claude-workflow`, `remote-runner` and plain `git push` commands. These tests use
synthetic rules; the shipped rule files for the new tools arrive in increment C.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "codex_approver.py"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_approver_tools_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = load_module()

BASE = {"collector": "commit", "checks": ["head_matches"], "rubric": "commit", "review_checks": ["scope_is_coherent"]}
SUBMIT = dict(BASE, id="remote-runner-submit", tool="remote-runner", subcommand="submit", required=["--profile"],
              flags={"--remote": "value", "--best": "bool", "--profile": "value", "--ref": "value",
                     "--snapshot": "bool"}, positionals="none")
FETCH = dict(BASE, id="remote-runner-fetch", tool="remote-runner", subcommand="fetch", required=[],
             flags={"--dest": "value", "--as": "value", "--force": "bool"}, positionals="two-or-more")
CANCEL = dict(BASE, id="remote-runner-cancel", tool="remote-runner", subcommand="cancel", required=[],
              flags={}, positionals="one")
PRUNE = dict(BASE, id="remote-runner-prune", tool="remote-runner", subcommand="prune", required=["--remote"],
             flags={"--remote": "value", "--success-days": "value", "--failure-days": "value", "--apply": "bool"},
             positionals="none")
PUSH = dict(BASE, id="git-push", tool="git", subcommand="push", required=[],
            flags={"--force": "bool", "-f": "bool", "--set-upstream": "bool", "-u": "bool", "--tags": "bool",
                   "--delete": "bool", "--dry-run": "bool", "-n": "bool"}, positionals="up-to-two")
RULES = [SUBMIT, FETCH, CANCEL, PRUNE, PUSH]
RUNNER_SPELLINGS = {
    "remote-runner", "~/.claude/bin/remote-runner", "~/.local/bin/remote-runner",
    "python3 ~/.claude/bin/remote-runner", "python3 -B ~/.claude/bin/remote-runner"}


def parse(command, rules=RULES):
    split = ca.split_command(command)
    if split is None:
        return None
    tokens = ca.tokenize(split[1])
    return None if tokens is None else ca.match_rule(tokens, rules, tool=ca.SPELLING_TOOL[split[0]])


class SplitTests(unittest.TestCase):
    def test_remote_runner_has_the_five_spellings_the_settings_list(self):
        self.assertEqual(set(ca.REMOTE_RUNNER_SPELLINGS), RUNNER_SPELLINGS)
        for spelling in RUNNER_SPELLINGS:
            with self.subTest(spelling=spelling):
                self.assertEqual(ca.split_command(spelling + " cancel job1"), (spelling, "cancel job1"))
                self.assertEqual(ca.SPELLING_TOOL[spelling], "remote-runner")

    def test_git_matches_only_the_bare_word(self):
        self.assertEqual(ca.split_command("git push origin main"), ("git", "push origin main"))
        self.assertEqual(ca.SPELLING_TOOL["git"], "git")

    def test_claude_workflow_spellings_are_unchanged(self):
        self.assertEqual(set(ca.SPELLINGS), {
            "claude-workflow", "~/.claude/bin/claude-workflow", "~/.local/bin/claude-workflow",
            "python3 ~/.claude/bin/claude-workflow", "python3 -B ~/.claude/bin/claude-workflow"})
        self.assertEqual(ca.SPELLING_TOOL["claude-workflow"], "claude-workflow")

    def test_lookalikes_do_not_split(self):
        for bad in (
            "git  push origin", "git\tpush", "gitx push", "/usr/bin/git push", "./git push", '"git" push',
            "env git push", "GIT_DIR=x git push", "cd x && git push", "sudo git push", "git", "git ",
            "remote-runner", "remote-runner  cancel j", "remote-runnerX cancel j", "/usr/local/bin/remote-runner cancel j",
            '"remote-runner" cancel j', "python3  ~/.claude/bin/remote-runner cancel j",
            "env remote-runner cancel j", "~/.claude/bin/remote-runner",
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(ca.split_command(bad))


class MatchTests(unittest.TestCase):
    def test_submit_and_its_flags(self):
        rule, args = parse("remote-runner submit --best --profile tests --snapshot")
        self.assertEqual(rule["id"], "remote-runner-submit")
        self.assertTrue(args["--best"] and args["--snapshot"])
        self.assertEqual(args["--profile"], "tests")
        self.assertEqual(args["paths"], [])

    def test_fetch_takes_a_job_and_one_or_more_paths(self):
        rule, args = parse("python3 -B ~/.claude/bin/remote-runner fetch --dest out job1 a.bin b/c.bin")
        self.assertEqual(rule["id"], "remote-runner-fetch")
        self.assertEqual(args["paths"], ["job1", "a.bin", "b/c.bin"])
        self.assertEqual(args["--dest"], "out")

    def test_cancel_and_prune(self):
        self.assertEqual(parse("remote-runner cancel job1")[1]["paths"], ["job1"])
        rule, args = parse("remote-runner prune --remote ned --apply --success-days 3")
        self.assertEqual(rule["id"], "remote-runner-prune")
        self.assertTrue(args["--apply"])
        self.assertEqual(args["--success-days"], "3")

    def test_git_push_shapes_and_short_flags(self):
        for command, positionals in (("git push", []), ("git push origin", ["origin"]),
                                     ("git push origin main", ["origin", "main"]),
                                     ("git push -u origin HEAD:refs/heads/x", ["origin", "HEAD:refs/heads/x"])):
            with self.subTest(command=command):
                rule, args = parse(command)
                self.assertEqual(rule["id"], "git-push")
                self.assertEqual(args["paths"], positionals)
        self.assertTrue(parse("git push -u origin main")[1]["-u"])
        self.assertTrue(parse("git push --force origin main")[1]["--force"])

    def test_shapes_outside_the_grammar_do_not_match(self):
        for bad in (
            "git push origin main extra", "git push --mirror", "git push --receive-pack=x origin",
            "git push -o x origin", "git push --force-with-lease origin", "git push --force=1",
            "git push origin 'a b'; ls", "git push origin $(id)", "git pull", "git commit -m x",
            "remote-runner submit", "remote-runner submit --profile", "remote-runner submit --profile a b",
            "remote-runner submit --profile a --bogus", "remote-runner submit --profile=a",
            "remote-runner fetch job1", "remote-runner cancel", "remote-runner cancel a b",
            "remote-runner prune", "remote-runner prune --remote ned extra", "remote-runner status job1",
            "remote-runner submit --profile a --profile b",
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(parse(bad))

    def test_the_tool_selects_the_rule(self):
        clash = dict(PUSH, id="clash", tool="remote-runner", subcommand="push")
        self.assertIsNone(ca.match_rule(["push"], [clash], tool="git"))
        self.assertIsNotNone(ca.match_rule(["push"], [clash], tool="remote-runner"))
        self.assertIsNotNone(ca.match_rule(["push"], [clash]))  # no tool given: the first matching subcommand

    def test_double_dash_still_separates_positionals(self):
        rule, args = parse("remote-runner fetch job1 -- -odd")
        self.assertEqual(args["paths"], ["job1", "-odd"])


class RuleValidationTests(unittest.TestCase):
    def test_the_new_tools_and_positional_kinds_are_accepted(self):
        for rule in RULES:
            with self.subTest(rule=rule["id"]):
                self.assertIs(ca.validate_rule(rule), rule)

    def test_unknown_tools_and_positionals_are_rejected(self):
        for label, rule in (("tool", dict(PUSH, tool="rm")), ("positionals", dict(PUSH, positionals="anything")),
                            ("short flag shape", dict(PUSH, flags={"-ab": "bool"})),
                            ("flag kind", dict(PUSH, flags={"-u": "maybe"}))):
            with self.subTest(label=label):
                with self.assertRaises(ca.ConfigError):
                    ca.validate_rule(rule)

    def test_paths_rules_keep_requiring_a_path(self):
        rule = dict(PUSH, positionals="paths", flags={})
        self.assertIsNone(ca.match_rule([rule["subcommand"]], [rule]))


class InvocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.home, self.bin, self.repo = base / "home", base / "bin", base / "repo"
        for directory in (self.home / ".claude" / "bin", self.home / ".local" / "bin", self.bin, self.repo / ".git"):
            directory.mkdir(parents=True)
        self.installed = self.home / ".claude" / "bin" / "remote-runner"
        self.installed.write_text("#!/usr/bin/env python3\n")
        self.installed.chmod(0o755)
        (self.home / ".local" / "bin" / "remote-runner").symlink_to(self.installed)
        (self.bin / "remote-runner").symlink_to(self.installed)
        (self.bin / "python3").symlink_to(sys.executable)
        self.git = self.bin / "git"
        self.git.write_text("#!/bin/sh\nexit 0\n")
        self.git.chmod(0o755)
        self.path_value = str(self.bin)

    def resolve(self, spelling, path_value=None):
        return ca.resolve_invocation(spelling, path_value if path_value is not None else self.path_value,
                                     str(self.home), str(self.repo), installed=str(self.installed))

    def test_every_remote_runner_spelling_resolves_to_the_installed_tool(self):
        for spelling in ca.REMOTE_RUNNER_SPELLINGS:
            with self.subTest(spelling=spelling):
                ok, why = self.resolve(spelling)
                self.assertTrue(ok, why)

    def test_a_different_remote_runner_is_refused(self):
        other = self.bin / "other"
        other.mkdir()
        (other / "remote-runner").write_text("#!/usr/bin/env python3\n")
        (other / "remote-runner").chmod(0o755)
        ok, why = self.resolve("remote-runner", path_value=str(other))
        self.assertEqual((ok, why), (False, "helper_is_not_the_installed_helper"))

    def test_git_resolves_from_an_absolute_entry_outside_the_repository(self):
        self.assertEqual(self.resolve("git"), (True, None))

    def test_git_inside_the_repository_or_on_a_relative_entry_is_refused(self):
        planted = self.repo / "bin"
        planted.mkdir()
        for directory in (planted, self.repo):
            (directory / "git").write_text("#!/bin/sh\nexit 0\n")
            (directory / "git").chmod(0o755)
        for entry in (str(planted), "", ".", "bin"):
            with self.subTest(entry=entry):
                ok, _why = self.resolve("git", path_value=os.pathsep.join([entry, str(self.bin)]))
                self.assertFalse(ok)

    def test_a_missing_git_is_refused(self):
        ok, why = self.resolve("git", path_value=str(self.repo / "nowhere"))
        self.assertEqual((ok, why), (False, "not_found:git"))


if __name__ == "__main__":
    unittest.main()
