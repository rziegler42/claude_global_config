"""Tests for the engine of hooks/codex_approver.py (spec: docs/specs/codex-approver.md).

Run from the repository root with:  python3 -B -m unittest discover -s tests

Nothing here runs Codex or a real helper. The hook is loaded as a module for unit
tests and copied beside a scratch data directory for end-to-end runs.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "codex_approver.py"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_approver_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = load_module()

COMMIT_RULE = {
    "id": "claude-workflow-commit", "tool": "claude-workflow", "subcommand": "commit",
    "collector": "commit", "checks": ["head_matches"], "rubric": "commit",
    "review_checks": ["message_matches_change"],
    "required": ["--expected-head", "--subject"],
    "flags": {"--expected-head": "value", "--subject": "value", "--body": "value",
              "--trailer": "multi", "--leave-other-staged": "bool"},
    "positionals": "paths",
}
REMOVE_RULE = {
    "id": "claude-workflow-remove", "tool": "claude-workflow", "subcommand": "remove",
    "collector": "remove", "checks": ["confirm_present"], "rubric": "remove",
    "review_checks": ["targets_look_disposable"],
    "required": ["--confirm"],
    "flags": {"--confirm": "bool", "--recursive": "bool"},
    "positionals": "paths",
}
CONFIG = {"mode": "advise", "model": "gpt-6.1-sol", "effort": "medium",
          "codex_timeout_seconds": 12, "max_log_bytes": 5242880, "notify": False, "delegate": []}
DELEGATING = dict(CONFIG, mode="delegate", delegate=["claude-workflow-commit"])


class TokenizeTests(unittest.TestCase):
    def test_plain_words(self):
        self.assertEqual(ca.tokenize("commit --expected-head abc123 a/b.txt"),
                         ["commit", "--expected-head", "abc123", "a/b.txt"])

    def test_single_quotes_are_literal(self):
        self.assertEqual(ca.tokenize("--subject 'Fix a; b && c $(x) `y`'"),
                         ["--subject", "Fix a; b && c $(x) `y`"])

    def test_empty_single_quoted_string_is_an_empty_token(self):
        self.assertEqual(ca.tokenize("--body ''"), ["--body", ""])

    def test_newline_inside_single_quotes_is_kept(self):
        self.assertEqual(ca.tokenize("--body 'a\nb'"), ["--body", "a\nb"])

    def test_double_quotes_without_expansion_characters(self):
        self.assertEqual(ca.tokenize('--subject "Add a thing"'), ["--subject", "Add a thing"])

    def test_rejected_inputs_return_none(self):
        for bad in (
            "a; b", "a && b", "a | b", "a > f", "a < f", "a & b", "a || b",
            "a $(x)", "a `x`", 'a "$HOME"', 'a "`x`"', 'a "x\\y"', 'a "x!"',
            "a\nb", "a 'unterminated", 'a "unterminated', "a\\ b", "a *.txt", "a [x]", "a ?",
            "a b'c'", "a 'b'c", "a (b)", "a {b}", "a #c", "a ~x?",
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(ca.tokenize(bad))

    def test_unicode_control_characters_in_bare_words_are_rejected(self):
        self.assertIsNone(ca.tokenize("a‮b"))
        self.assertIsNone(ca.tokenize("a\x00b"))

    def test_a_leading_equals_sign_is_refused_because_zsh_expands_it(self):
        # zsh turns an unquoted `=ls` into the absolute path of ls (MAGIC_EQUAL_SUBST family).
        self.assertIsNone(ca.tokenize("commit =ls"))
        self.assertEqual(ca.tokenize("--subject '=ls'"), ["--subject", "=ls"])
        self.assertEqual(ca.tokenize("a=b"), ["a=b"])


class SplitCommandTests(unittest.TestCase):
    def test_all_five_spellings(self):
        for spelling in ca.SPELLINGS:
            with self.subTest(spelling=spelling):
                got = ca.split_command(spelling + " commit a")
                self.assertEqual(got, (spelling, "commit a"))

    def test_spelling_list_matches_the_settings_rules(self):
        self.assertEqual(set(ca.SPELLINGS), {
            "claude-workflow", "~/.claude/bin/claude-workflow", "~/.local/bin/claude-workflow",
            "python3 ~/.claude/bin/claude-workflow", "python3 -B ~/.claude/bin/claude-workflow"})

    def test_quoted_or_partly_quoted_executable_does_not_match(self):
        for bad in (
            '"~/.claude/bin/claude-workflow" commit a', "'~/.claude/bin/claude-workflow' commit a",
            '~/".claude/bin/claude-workflow" commit a', '"claude-workflow" commit a',
            "python3 '~/.claude/bin/claude-workflow' commit a",
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(ca.split_command(bad))

    def test_lookalikes_and_whitespace_variants_do_not_match(self):
        for bad in (
            " claude-workflow commit a", "claude-workflow  commit a", "claude-workflow\tcommit a",
            "claude-workflowX commit a", "/usr/local/bin/claude-workflow commit a",
            "./claude-workflow commit a", "python3  ~/.claude/bin/claude-workflow commit a",
            "python3 -B  ~/.claude/bin/claude-workflow commit a", "env claude-workflow commit a",
            "PATH=. claude-workflow commit a", "cd x && claude-workflow commit a",
            "claude-workflow", "claude-workflow ", "python3 ~/.claude/bin/claude-workflow",
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(ca.split_command(bad))


class MatchRuleTests(unittest.TestCase):
    def match(self, rest, rules=(COMMIT_RULE, REMOVE_RULE)):
        return ca.match_rule(ca.tokenize(rest), list(rules))

    def test_commit_matches_and_parses_arguments(self):
        rule, args = self.match("commit --expected-head abc --subject 'Add x' --trailer 'A: b' --trailer 'C: d' f1 d/f2")
        self.assertEqual(rule["id"], "claude-workflow-commit")
        self.assertEqual(args["--expected-head"], "abc")
        self.assertEqual(args["--subject"], "Add x")
        self.assertEqual(args["--trailer"], ["A: b", "C: d"])
        self.assertEqual(args["paths"], ["f1", "d/f2"])
        self.assertFalse(args.get("--leave-other-staged"))

    def test_double_dash_separates_paths(self):
        _, args = self.match("commit --expected-head abc --subject s -- -odd f2")
        self.assertEqual(args["paths"], ["-odd", "f2"])

    def test_bool_flag_and_remove(self):
        rule, args = self.match("remove --recursive --confirm dir1 f2")
        self.assertEqual(rule["id"], "claude-workflow-remove")
        self.assertTrue(args["--confirm"])
        self.assertTrue(args["--recursive"])
        self.assertEqual(args["paths"], ["dir1", "f2"])

    def test_no_match_cases(self):
        for bad in (
            "commit --subject s f1",                       # missing required flag
            "commit --expected-head abc f1",               # missing required flag
            "commit --expected-head abc --subject s",      # no paths
            "commit --expected-head abc --subject s --bogus f1",  # unknown flag
            "commit --expected-head=abc --subject s f1",   # attached form is not accepted
            "commit --expected-head --subject s f1",       # value looks like a flag
            "commit --expected-head abc --expected-head def --subject s f1",  # repeated single
            "remove f1",                                   # --confirm required
            "amend-message --expected-head a --subject s",  # no rule for the subcommand
            "frobnicate", "",
        ):
            with self.subTest(bad=bad):
                tokens = ca.tokenize(bad)
                self.assertIsNone(ca.match_rule(tokens, [COMMIT_RULE, REMOVE_RULE]) if tokens else None)


class ConfigAndRuleLoadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, name, value):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        return path

    def test_load_config_accepts_the_shipped_shape(self):
        self.assertEqual(ca.load_config(self.write("config.json", CONFIG)), CONFIG)

    def test_load_config_rejects_bad_input(self):
        bad_values = [
            dict(CONFIG, mode="allow"), dict(CONFIG, mode="deny"), dict(CONFIG, mode=None),
            dict(CONFIG, extra=1), dict(CONFIG, codex_timeout_seconds="12"),
            dict(CONFIG, codex_timeout_seconds=0), dict(CONFIG, codex_timeout_seconds=1000),
            dict(CONFIG, notify="yes"), dict(CONFIG, max_log_bytes=10), "not json", "[]",
            {k: v for k, v in CONFIG.items() if k != "mode"},
            {k: v for k, v in CONFIG.items() if k != "delegate"},
            # advice-only mode must not carry a delegation list, and delegate mode needs one
            dict(CONFIG, delegate=["claude-workflow-commit"]), dict(DELEGATING, delegate=[]),
            # only the commit and archive rules are on the ceiling; anything else, duplicates and bad shapes are refused
            dict(DELEGATING, delegate=["git-push"]), dict(DELEGATING, delegate=["claude-workflow-remove"]),
            dict(DELEGATING, delegate=["claude-workflow-commit", "git-push"]),
            dict(DELEGATING, delegate=["ask-codex-archive", "git-push"]),
            dict(DELEGATING, delegate=["ask-codex-prune"]),
            dict(DELEGATING, delegate=["claude-workflow-commit", "claude-workflow-commit"]),
            dict(DELEGATING, delegate="claude-workflow-commit"), dict(DELEGATING, delegate=[None]),
            dict(DELEGATING, delegate=[["claude-workflow-commit"]]), dict(DELEGATING, delegate=None),
            dict(DELEGATING, delegate=["CLAUDE-WORKFLOW-COMMIT"]), dict(DELEGATING, delegate=["unknown-rule"]),
            dict(DELEGATING, mode="Delegate"), dict(DELEGATING, mode=["delegate"]),
        ]
        for value in bad_values:
            with self.subTest(value=value):
                path = self.write("config.json", value)
                with self.assertRaises(ca.ConfigError):
                    ca.load_config(path)

    def test_load_config_accepts_delegation_of_the_commit_and_archive_rules_only(self):
        self.assertEqual(ca.load_config(self.write("config.json", DELEGATING)), DELEGATING)
        both = dict(DELEGATING, delegate=["claude-workflow-commit", "ask-codex-archive"])
        self.assertEqual(ca.load_config(self.write("config.json", both)), both)
        archive = dict(DELEGATING, delegate=["ask-codex-archive"])
        self.assertEqual(ca.load_config(self.write("config.json", archive)), archive)
        self.assertEqual(ca.DELEGABLE, frozenset({"claude-workflow-commit", "ask-codex-archive"}))

    def test_load_config_missing_file_is_an_error(self):
        with self.assertRaises(ca.ConfigError):
            ca.load_config(self.dir / "absent.json")

    def test_load_rules_reads_every_json_file_sorted(self):
        self.write("rules/b.json", dict(REMOVE_RULE, id="b"))
        self.write("rules/a.json", dict(COMMIT_RULE, id="a"))
        self.assertEqual([r["id"] for r in ca.load_rules(self.dir / "rules")], ["a", "b"])

    def test_load_rules_rejects_bad_rules(self):
        cases = {
            "duplicate id": [dict(COMMIT_RULE), dict(COMMIT_RULE)],
            "unknown key": [dict(COMMIT_RULE, surprise=1)],
            "missing key": [{k: v for k, v in COMMIT_RULE.items() if k != "collector"}],
            "wrong type": [dict(COMMIT_RULE, checks="head_matches")],
            "bad flag kind": [dict(COMMIT_RULE, flags={"--x": "whatever"})],
            "flag without dashes": [dict(COMMIT_RULE, flags={"x": "bool"})],
            "required not declared": [dict(COMMIT_RULE, required=["--nope"])],
            "bad tool": [dict(COMMIT_RULE, tool="rm")],
            "bad id": [dict(COMMIT_RULE, id="has space")],
            "bad review check": [dict(COMMIT_RULE, review_checks=["Has Space"])],
            "review checks wrong type": [dict(COMMIT_RULE, review_checks="x")],
            "no review checks": [dict(COMMIT_RULE, review_checks=[])],
        }
        for label, rules in cases.items():
            with self.subTest(label=label):
                directory = self.dir / ("rules-" + label.replace(" ", "-"))
                for number, rule in enumerate(rules):
                    self.write("%s/r%d.json" % (directory.name, number), rule)
                with self.assertRaises(ca.ConfigError):
                    ca.load_rules(directory)

    def test_load_rules_rejects_unparseable_json(self):
        self.write("rules/x.json", "{")
        with self.assertRaises(ca.ConfigError):
            ca.load_rules(self.dir / "rules")


class LogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "log" / "verdicts.jsonl"

    def test_appends_json_lines_with_private_mode(self):
        ca.append_log(self.log, {"n": 1}, 5_000_000)
        ca.append_log(self.log, {"n": 2}, 5_000_000)
        lines = self.log.read_text().splitlines()
        self.assertEqual([json.loads(line)["n"] for line in lines], [1, 2])
        self.assertEqual(stat.S_IMODE(self.log.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.log.parent.stat().st_mode), 0o700)

    def test_rotates_once_at_the_cap(self):
        ca.append_log(self.log, {"n": "x" * 200}, 300)
        ca.append_log(self.log, {"n": "y" * 200}, 300)
        ca.append_log(self.log, {"n": "z" * 200}, 300)
        rotated = self.log.with_name(self.log.name + ".1")
        self.assertTrue(rotated.exists())
        self.assertLessEqual(self.log.stat().st_size, 300)
        self.assertFalse(self.log.with_name(self.log.name + ".2").exists())

    def test_refuses_a_symlinked_log(self):
        self.log.parent.mkdir(parents=True)
        target = Path(self.tmp.name) / "elsewhere"
        target.write_text("")
        self.log.symlink_to(target)
        with self.assertRaises(OSError):
            ca.append_log(self.log, {"n": 1}, 5_000_000)
        self.assertEqual(target.read_text(), "")


class NotifyTests(unittest.TestCase):
    def test_passes_fixed_strings_as_arguments_never_in_script_text(self):
        calls = []
        ca.notify("claude-workflow-commit", "approve", runner=lambda argv, **kw: calls.append(argv),
                  platform="darwin", exists=lambda path: True)
        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertEqual(argv[0], "/usr/bin/osascript")
        script = argv[argv.index("-e") + 1] if "-e" in argv else ""
        self.assertNotIn("claude-workflow-commit", script)
        self.assertIn("claude-workflow-commit", argv)
        self.assertIn("approve", argv)

    def test_hostile_rule_id_or_verdict_sends_nothing(self):
        calls = []
        for rule, verdict in (("x\"; do shell script \"id", "approve"), ("ok", "allow"), ("ok", "x" * 5)):
            ca.notify(rule, verdict, runner=lambda argv, **kw: calls.append(argv),
                      platform="darwin", exists=lambda path: True)
        self.assertEqual(calls, [])

    def test_no_op_off_macos_or_without_osascript(self):
        calls = []
        ca.notify("ok", "approve", runner=lambda argv, **kw: calls.append(argv), platform="linux",
                  exists=lambda path: True)
        ca.notify("ok", "approve", runner=lambda argv, **kw: calls.append(argv), platform="darwin",
                  exists=lambda path: False)
        self.assertEqual(calls, [])

    def test_runner_failure_is_swallowed(self):
        def boom(argv, **kw):
            raise OSError("no")
        ca.notify("ok", "approve", runner=boom, platform="darwin", exists=lambda path: True)

    def test_the_executable_is_a_fixed_absolute_path_never_looked_up_on_path(self):
        self.assertEqual(ca.NOTIFIER, "/usr/bin/osascript")
        calls = []
        ca.notify("ok", "approve", runner=lambda argv, **kw: calls.append(argv), platform="darwin",
                  exists=lambda path: True)
        self.assertEqual(calls[0][0], "/usr/bin/osascript")


class HookProcessTests(unittest.TestCase):
    """End-to-end: the hook as a subprocess beside a scratch data directory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        (base / "hooks").mkdir()
        shutil.copy2(HOOK, base / "hooks" / "codex_approver.py")
        data = base / "codex-approver"
        (data / "rules").mkdir(parents=True)
        (data / "config.json").write_text(json.dumps(CONFIG))
        (data / "rules" / "commit.json").write_text(json.dumps(COMMIT_RULE))
        (data / "rules" / "remove.json").write_text(json.dumps(REMOVE_RULE))
        self.base = base
        self.data = data
        self.script = base / "hooks" / "codex_approver.py"

    def run_hook(self, stdin):
        env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
        return subprocess.run([sys.executable, "-B", str(self.script)], input=stdin, capture_output=True,
                              text=True, env=env, timeout=60)

    def event(self, command, tool="Bash", **extra):
        payload = {"hook_event_name": "PermissionRequest", "tool_name": tool,
                   "tool_input": {"command": command}, "cwd": str(self.base), "permission_mode": "auto",
                   "session_id": "s1"}
        payload.update(extra)
        return json.dumps(payload)

    def log_entries(self):
        path = self.data / "log" / "verdicts.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_matching_command_is_logged_and_nothing_is_printed(self):
        r = self.run_hook(self.event("claude-workflow commit --expected-head abc --subject 'Add x' f1"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        entries = self.log_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["rule"], "claude-workflow-commit")
        # The scratch tree has no installed helper, so the invocation check declines it.
        self.assertEqual(entries[0]["verdict"], "decline")
        self.assertIn("invocation_trusted", entries[0]["failed_checks"])

    def test_unmatched_command_prints_nothing_and_logs_nothing(self):
        for command in ("ls -la", "git commit -m x", "claude-workflow context", "echo hi; claude-workflow commit a"):
            with self.subTest(command=command):
                r = self.run_hook(self.event(command))
                self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.log_entries(), [])

    def test_non_bash_tools_are_ignored(self):
        r = self.run_hook(self.event("claude-workflow commit --expected-head a --subject s f", tool="Write"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.log_entries(), [])

    def test_stdout_is_empty_for_every_malformed_input(self):
        good = json.loads(self.event("ls"))
        inputs = [
            "", "not json", "[]", "null", "42", '"str"', "{}", "{\"tool_name\": 1}",
            json.dumps(dict(good, tool_input=None)), json.dumps(dict(good, tool_input=[])),
            json.dumps(dict(good, tool_input={"command": 5})), json.dumps(dict(good, tool_input={"command": None})),
            json.dumps(dict(good, tool_input={"command": "claude-workflow commit " + "a " * 100000})),
            json.dumps(dict(good, tool_input={"command": "claude-workflow commit \x00"})),
            json.dumps(dict(good, cwd=None)), json.dumps(dict(good, cwd="/nonexistent/dir")),
            "﻿" + json.dumps(good), "{" * 5000,
        ]
        for stdin in inputs:
            with self.subTest(stdin=stdin[:60]):
                r = self.run_hook(stdin)
                self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_broken_config_or_rules_print_nothing(self):
        (self.data / "config.json").write_text(json.dumps(dict(CONFIG, mode="allow")))
        r = self.run_hook(self.event("claude-workflow commit --expected-head a --subject s f"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        (self.data / "config.json").write_text(json.dumps(CONFIG))
        (self.data / "rules" / "bad.json").write_text("{")
        r = self.run_hook(self.event("claude-workflow commit --expected-head a --subject s f"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.log_entries(), [])

    def test_log_entry_has_no_command_text_beyond_the_rule_and_digest(self):
        self.run_hook(self.event("claude-workflow commit --expected-head abc --subject 'SECRET-SUBJECT' f1"))
        raw = (self.data / "log" / "verdicts.jsonl").read_text()
        self.assertNotIn("SECRET-SUBJECT", raw)
        entry = json.loads(raw.splitlines()[0])
        self.assertRegex(entry["command_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
