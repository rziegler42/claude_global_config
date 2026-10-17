"""Tests for the unmatched-prompt log of hooks/codex_approver.py (plan: docs/plans/next.md, increment F).

Run from the repository root with:  python3 -B -m unittest discover -s tests -p 'test_codex_approver_unmatched.py'

A prompt that matches no rule is recorded as a shape only (never arguments) in log/unmatched.jsonl.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_codex_approver_rules import HOOK, ROOT, ca


class ShapeTests(unittest.TestCase):
    def shape(self, command):
        return ca.command_shape(command)

    def test_a_plain_command_has_a_shape_and_no_arguments(self):
        info = self.shape("git ls-tree -r HEAD docs/secret-plan.md")
        self.assertEqual((info["shape"], info["compound"], info["segments"]), ("git ls-tree", False, []))
        self.assertEqual(self.shape("cat README.md")["shape"], "cat")
        self.assertEqual(self.shape("uv run pytest -q")["shape"], "uv run")

    def test_option_after_the_tool_stops_the_shape(self):
        self.assertEqual(self.shape("git -C /some/where status")["shape"], "git")
        self.assertEqual(self.shape("python3 -B -m unittest")["shape"], "python3")

    def test_environment_prefixes_are_skipped(self):
        self.assertEqual(self.shape("FOO=bar BAZ=1 uv run pytest")["shape"], "uv run")

    def test_compound_commands_list_each_segment_and_skip_cd_and_assignments(self):
        info = self.shape("cd /x/y; J=ned--a--1; remote-runner cancel $J 2>&1 | tail -5")
        self.assertTrue(info["compound"])
        self.assertEqual(info["shape"], "remote-runner cancel")
        self.assertEqual(info["segments"], ["remote-runner cancel", "tail"])
        info = self.shape("git push origin main 2>&1 | tail -1 && remote-runner submit --best 2>&1 | grep job")
        self.assertEqual(info["segments"], ["git push", "tail", "remote-runner submit", "grep"])

    def test_quoted_operators_do_not_make_a_command_compound(self):
        info = self.shape("git commit -m 'a; b && c | d'")
        self.assertEqual((info["shape"], info["compound"]), ("git commit", False))
        self.assertTrue(self.shape('echo "$(whoami)"')["compound"])
        self.assertTrue(self.shape("echo `whoami`")["compound"])
        self.assertFalse(self.shape("echo '$(whoami)'")["compound"])

    def test_shell_keywords_are_not_commands(self):
        info = self.shape("J=x; until ! remote-runner status $J | grep -q go; do sleep 60; done; date")
        self.assertEqual(info["segments"], ["remote-runner status", "grep", "sleep", "date"])
        info = self.shape("for c in a b; do command -v $c || echo missing; done")
        self.assertEqual(info["segments"], ["command", "echo"])

    def test_quoted_and_escaped_text_never_becomes_a_program(self):
        for command in ("PASSWORD='alpha bravo charlie' mytool", 'A="my secret pw here" mytool',
                        "PW=alpha\\ bravo\\ charlie mytool"):
            with self.subTest(command=command):
                info = self.shape(command)
                self.assertEqual((info["shape"], info["segments"]), ("mytool", []))

    def test_text_after_a_command_substitution_stays_an_argument(self):
        for command, shape, segments in (
                ("ls $(pwd) mysecretfile", "ls", ["ls", "pwd"]),
                ("$(git rev-parse --show-toplevel)/secrets/prod.env", "<other>", ["<other>", "git rev-parse"]),
                ("ls `pwd` mysecretfile", "ls", ["ls", "pwd"]),
                ("cat $(echo $(whoami)) notes", "cat", ["cat", "whoami", "echo"])):
            with self.subTest(command=command):
                info = self.shape(command)
                self.assertEqual((info["shape"], info["segments"]), (shape, segments))
                self.assertNotIn("secrets", json.dumps(info))
                self.assertNotIn("mysecretfile", json.dumps(info))

    def test_free_text_is_never_a_subcommand_and_odd_programs_are_bucketed(self):
        for command, shape in (("ask-codex hunter2 more", "ask-codex"), ("docker supersecretcontainername", "docker"),
                               ("make deploy-prod-aws-key", "make"), ("../../etc/passwd", "passwd"),
                               ("~/bin/hunter2password", "<other>"), ("/home/u/.ssh/id_rsa_work", "<other>"),
                               ("deadbeefdeadbeef01", "<other>"), ("ask-codex archive", "ask-codex archive"),
                               ("python3.12 -c x", "python3.12")):
            with self.subTest(command=command):
                self.assertEqual(self.shape(command)["shape"], shape)

    def test_a_heredoc_body_is_not_scanned(self):
        info = self.shape("cat > f.py <<'EOF'\nimport os\nprint(os.environ)\nEOF")
        self.assertEqual((info["shape"], info["heredoc"], info["segments"]), ("cat", True, []))

    def test_odd_words_never_reach_the_shape(self):
        token = "ghp_" + "e" * 36
        for command in (token + " status", "git " + token, "x" * 500, "git ls\x00tree", "\x1b[31mgit status", ""):
            with self.subTest(command=command[:20]):
                shape = self.shape(command)["shape"] if command else None
                self.assertNotIn(token, json.dumps(shape))
                self.assertTrue(shape is None or len(shape) <= 80)

    def test_segment_count_is_capped(self):
        info = self.shape("; ".join(["ls", "git status"] * 20))
        self.assertLessEqual(len(info["segments"]), 8)


class HostileLogTests(unittest.TestCase):
    def test_report_text_has_no_control_characters(self):
        rows = [{"ts": "2026-10-17T10:00:00+00:00", "shape": "\x1b]0;PWNED\x07\x1b[2J", "compound": True,
                 "segments": ["\x1b[31mred"]}]
        text = ca.format_unmatched_report(ca.build_unmatched_report(rows))
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)

    def test_malformed_rows_do_not_break_the_report(self):
        rows = [{"ts": "2026-10-17T10:00:00+00:00", "shape": "ok", "segments": 5},
                {"ts": "2026-10-17T10:00:00+00:00", "shape": "ok", "segments": [1, None, {"a": 1}]},
                {"ts": "2026-10-17T10:00:00+00:00", "shape": 7}, {"ts": 5, "shape": "x"}]
        report = ca.build_unmatched_report(rows)
        self.assertEqual([(i["shape"], i["count"]) for i in report["shapes"]], [("ok", 2)])

    def test_deeply_nested_json_and_a_huge_days_value_fail_quietly(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        claude = home / ".claude"
        (claude / "hooks").mkdir(parents=True)
        shutil.copy2(HOOK, claude / "hooks" / "codex_approver.py")
        shutil.copytree(ROOT / "codex-approver", claude / "codex-approver", ignore=shutil.ignore_patterns("log"))
        log = claude / "codex-approver" / "log"
        log.mkdir()
        (log / "unmatched.jsonl").write_text(
            "[" * 100000 + "\n" + json.dumps({"ts": "2026-10-17T10:00:00+00:00", "shape": "kept"}) + "\n")
        hook = str(claude / "hooks" / "codex_approver.py")
        run = subprocess.run([sys.executable, "-B", hook, "--report", "--unmatched"], capture_output=True, text=True,
                             env={"HOME": str(home)}, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("kept", run.stdout)
        run = subprocess.run([sys.executable, "-B", hook, "--report", "--unmatched", "--days", "99999999999999"],
                             capture_output=True, text=True, env={"HOME": str(home)}, timeout=60)
        self.assertEqual(run.returncode, 2)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        claude = self.home / ".claude"
        (claude / "hooks").mkdir(parents=True)
        shutil.copy2(HOOK, claude / "hooks" / "codex_approver.py")
        shutil.copytree(ROOT / "codex-approver", claude / "codex-approver", ignore=shutil.ignore_patterns("log"))
        config = json.loads((claude / "codex-approver" / "config.json").read_text())
        config["notify"] = False
        (claude / "codex-approver" / "config.json").write_text(json.dumps(config))
        self.claude = claude
        self.cwd = Path(self.tmp.name).resolve()

    def fire(self, command, event="PermissionRequest", tool="Bash", raw=None):
        payload = {"hook_event_name": event, "tool_name": tool, "cwd": str(self.cwd), "session_id": "s",
                   "tool_use_id": "t", "tool_input": {"command": command}, "permission_mode": "auto"}
        run = subprocess.run([sys.executable, "-B", str(self.claude / "hooks" / "codex_approver.py")],
                             input=raw if raw is not None else json.dumps(payload), capture_output=True, text=True,
                             env={"HOME": str(self.home), "PATH": "/usr/bin:/bin"}, timeout=60)
        self.assertEqual((run.returncode, run.stdout), (0, ""), run.stderr)

    def rows(self, name="unmatched.jsonl"):
        log = self.claude / "codex-approver" / "log" / name
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def test_an_unmatched_prompt_writes_one_shape_row(self):
        self.fire("git ls-tree -r HEAD secret-file.txt")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["shape"], rows[0]["compound"], rows[0]["session_id"]), ("git ls-tree", False, "s"))
        self.assertNotIn("secret-file", json.dumps(rows[0]))
        self.assertEqual(len(rows[0]["command_sha256"]), 64)

    def test_a_command_a_rule_covers_writes_no_unmatched_row(self):
        self.fire("claude-workflow remove --confirm nothing.txt")
        self.assertEqual(self.rows(), [])
        self.assertEqual(len(self.rows("verdicts.jsonl")), 1)

    def test_a_piped_rule_command_is_unmatched_and_compound(self):
        self.fire("remote-runner submit --best --profile tests 2>&1 | grep job")
        row, = self.rows()
        self.assertEqual((row["shape"], row["compound"], row["segments"]), (
            "remote-runner submit", True, ["remote-runner submit", "grep"]))
        self.assertEqual(self.rows("verdicts.jsonl"), [])

    def test_other_events_and_tools_write_nothing(self):
        self.fire("git status", event="PostToolUse")
        self.fire("git status", tool="Read")
        self.fire("git status", event="PreToolUse")
        self.fire("", raw="not json")
        self.fire("", raw=json.dumps({"hook_event_name": "PermissionRequest", "tool_name": "Bash",
                                       "tool_input": {"command": 5}}))
        self.assertEqual(self.rows(), [])

    def test_a_log_failure_still_exits_quietly(self):
        (self.claude / "codex-approver" / "log").write_text("a file where the directory should be")
        self.fire("git status")

    def test_a_huge_command_is_bounded(self):
        self.fire("git status " + "a" * 200000)
        row, = self.rows()
        self.assertEqual(row["shape"], "git status")

    def test_rotation_at_the_size_cap(self):
        config_path = self.claude / "codex-approver" / "config.json"
        config = json.loads(config_path.read_text())
        config["max_log_bytes"] = 1024
        config_path.write_text(json.dumps(config))
        for _ in range(30):
            self.fire("git status")
        log = self.claude / "codex-approver" / "log"
        self.assertTrue((log / "unmatched.jsonl.1").exists())
        self.assertLessEqual((log / "unmatched.jsonl").stat().st_size, 1024)


class ReportTests(unittest.TestCase):
    ROWS = [
        {"ts": "2026-10-17T10:00:00+00:00", "shape": "git ls-tree", "compound": False, "segments": []},
        {"ts": "2026-10-17T11:00:00+00:00", "shape": "git ls-tree", "compound": False, "segments": []},
        {"ts": "2026-10-17T12:00:00+00:00", "shape": "remote-runner submit", "compound": True,
         "segments": ["remote-runner submit", "grep"]},
        {"ts": "2026-09-01T12:00:00+00:00", "shape": "old thing", "compound": False, "segments": []},
        {"ts": "bad", "shape": "bad time", "compound": False, "segments": []},
    ]

    def test_shapes_are_ranked_with_compound_share_and_dates(self):
        now = ca.parse_ts("2026-10-17T13:00:00+00:00")
        report = ca.build_unmatched_report(self.ROWS, now=now, days=7)
        self.assertEqual([item["shape"] for item in report["shapes"]], ["git ls-tree", "remote-runner submit"])
        top = report["shapes"][0]
        self.assertEqual((top["count"], top["compound"], top["first"], top["last"]), (
            2, 0, "2026-10-17T10:00:00+00:00", "2026-10-17T11:00:00+00:00"))
        self.assertEqual(report["segments"][0], {"shape": "remote-runner submit", "count": 1})
        text = ca.format_unmatched_report(report)
        self.assertIn("git ls-tree", text)
        self.assertIn("Prompts matching no rule", text)

    def test_empty_report(self):
        self.assertIn("No unmatched prompts", ca.format_unmatched_report(ca.build_unmatched_report([], days=None)))

    def test_cli_option(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        claude = home / ".claude"
        (claude / "hooks").mkdir(parents=True)
        shutil.copy2(HOOK, claude / "hooks" / "codex_approver.py")
        shutil.copytree(ROOT / "codex-approver", claude / "codex-approver", ignore=shutil.ignore_patterns("log"))
        log = claude / "codex-approver" / "log"
        log.mkdir()
        (log / "unmatched.jsonl").write_text(json.dumps(
            {"ts": "2026-10-17T10:00:00+00:00", "shape": "uv run", "compound": False, "segments": []}) + "\n")
        run = subprocess.run([sys.executable, "-B", str(claude / "hooks" / "codex_approver.py"), "--report",
                              "--unmatched"], capture_output=True, text=True, env={"HOME": str(home)}, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("uv run", run.stdout)
        bad = subprocess.run([sys.executable, "-B", str(claude / "hooks" / "codex_approver.py"), "--report",
                              "--unmatched", "--days", "x"], capture_output=True, text=True,
                             env={"HOME": str(home)}, timeout=60)
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
