"""Tests for the outcome log and the agreement report of hooks/codex_approver.py.

The approver records a verdict when a prompt appears. PostToolUse and PostToolUseFailure record whether the command
then ran, so the owner can compare what the approver would have advised with what happened. Output is never logged.

Run from the repository root with:  python3 -B -m unittest discover -s tests
"""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "codex_approver.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_codex_approver_engine import COMMIT_RULE, CONFIG, REMOVE_RULE  # noqa: E402


def load_module():
    spec = importlib.util.spec_from_file_location("codex_approver_outcomes_under_test", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ca = load_module()
COMMAND = "claude-workflow commit --expected-head abc --subject 'Add x' f1"
SECRET = "TOP-SECRET-OUTPUT-1234"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class HookCase(unittest.TestCase):
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
        self.base, self.data = base, data
        self.script = base / "hooks" / "codex_approver.py"

    def run_hook(self, event=None, args=(), stdin=None):
        env = {k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ}
        payload = stdin if stdin is not None else json.dumps(event)
        return subprocess.run([sys.executable, "-B", str(self.script), *args], input=payload, capture_output=True,
                              text=True, env=env, timeout=60)

    def post(self, command=COMMAND, name="PostToolUse", **extra):
        event = {"hook_event_name": name, "tool_name": "Bash", "tool_input": {"command": command},
                 "session_id": "sess-1", "tool_use_id": "toolu_abc", "cwd": str(self.base), "duration_ms": 42,
                 "permission_mode": "auto"}
        if name == "PostToolUse":
            event["tool_response"] = {"stdout": SECRET, "stderr": "", "interrupted": False}
        else:
            event["error"] = "Exit code 3\n" + SECRET
            event["is_interrupt"] = False
        event.update(extra)
        return event

    def outcomes(self):
        path = self.data / "log" / "outcomes.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def verdicts(self):
        path = self.data / "log" / "verdicts.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class OutcomeRecordingTests(HookCase):
    def test_a_successful_run_is_recorded_without_its_output(self):
        r = self.run_hook(self.post())
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        (entry,) = self.outcomes()
        self.assertEqual((entry["rule"], entry["outcome"], entry["exit_code"]), ("claude-workflow-commit", "ran", 0))
        self.assertEqual((entry["session_id"], entry["tool_use_id"], entry["duration_ms"]), ("sess-1", "toolu_abc", 42))
        self.assertEqual(entry["command_sha256"], sha(COMMAND))
        self.assertNotIn(SECRET, (self.data / "log" / "outcomes.jsonl").read_text())

    def test_a_failed_run_is_recorded_with_its_exit_code_only(self):
        r = self.run_hook(self.post(name="PostToolUseFailure"))
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        (entry,) = self.outcomes()
        self.assertEqual((entry["outcome"], entry["exit_code"]), ("ran_failed", 3))
        self.assertNotIn(SECRET, (self.data / "log" / "outcomes.jsonl").read_text())

    def test_an_interrupted_run_is_flagged(self):
        self.run_hook(self.post(name="PostToolUseFailure", is_interrupt=True, error="interrupted"))
        (entry,) = self.outcomes()
        self.assertEqual((entry["outcome"], entry["exit_code"], entry["interrupted"]), ("ran_failed", None, True))

    def test_the_command_digest_matches_the_one_in_the_verdict_log(self):
        prompt = {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": COMMAND},
                  "cwd": str(self.base), "session_id": "sess-1", "permission_mode": "auto"}
        self.run_hook(prompt)
        self.run_hook(self.post())
        self.assertEqual(self.verdicts()[0]["command_sha256"], self.outcomes()[0]["command_sha256"])
        self.assertEqual(self.verdicts()[0]["session_id"], "sess-1")

    def test_other_commands_tools_and_events_record_nothing(self):
        for event in (self.post(command="ls -la"), self.post(command="echo hi; " + COMMAND),
                      self.post(tool_name="Write"), self.post(name="PostToolUse", tool_input={"command": 5})):
            with self.subTest(event=event.get("tool_input")):
                r = self.run_hook(event)
                self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.outcomes(), [])

    def test_malformed_input_and_broken_config_stay_silent(self):
        for stdin in ("", "not json", "[]", "null", json.dumps(self.post(session_id=["x"])),
                      json.dumps(self.post(duration_ms="long")), json.dumps(self.post(cwd=None))):
            with self.subTest(stdin=stdin[:40]):
                r = self.run_hook(stdin=stdin)
                self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        (self.data / "config.json").write_text("{")
        r = self.run_hook(self.post())
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_hostile_identifiers_are_not_logged_verbatim(self):
        self.run_hook(self.post(session_id="a" * 500, tool_use_id="x\ny;rm -rf"))
        (entry,) = self.outcomes()
        self.assertIsNone(entry["session_id"])
        self.assertIsNone(entry["tool_use_id"])

    def test_the_outcome_log_is_private(self):
        self.run_hook(self.post())
        path = self.data / "log" / "outcomes.jsonl"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


def iso(seconds):
    base = datetime.datetime(2026, 10, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)
    return (base + datetime.timedelta(seconds=seconds)).isoformat(timespec="seconds")


def verdict(seconds, outcome, rule="claude-workflow-commit", digest="d1", session="s1", **extra):
    entry = {"ts": iso(seconds), "rule": rule, "verdict": outcome, "failed_checks": [], "command_sha256": digest,
             "session_id": session, "reason_text": "because"}
    entry.update(extra)
    return entry


def outcome(seconds, kind="ran", digest="d1", session="s1", rule="claude-workflow-commit"):
    return {"ts": iso(seconds), "rule": rule, "outcome": kind, "command_sha256": digest, "session_id": session,
            "exit_code": 0 if kind == "ran" else 1}


NOW = datetime.datetime(2026, 10, 16, 14, 0, 0, tzinfo=datetime.timezone.utc)


class ReportTests(unittest.TestCase):
    def report(self, verdicts, outcomes, **kw):
        return ca.build_report(verdicts, outcomes, now=NOW, **kw)

    def test_pairs_each_verdict_with_what_happened(self):
        report = self.report(
            [verdict(0, "approve", digest="a"), verdict(10, "approve", digest="b"), verdict(20, "decline", digest="c"),
             verdict(30, "decline", digest="d"), verdict(40, "no_verdict", digest="e")],
            [outcome(5, "ran", digest="a"), outcome(25, "ran", digest="c"), outcome(45, "ran_failed", digest="e")])
        m = report["matrix"]
        self.assertEqual(m["approve"], {"ran": 1, "ran_failed": 0, "not_run": 1})
        self.assertEqual(m["decline"], {"ran": 1, "ran_failed": 0, "not_run": 1})
        self.assertEqual(m["no_verdict"], {"ran": 0, "ran_failed": 1, "not_run": 0})
        self.assertEqual(report["agreement"], {"agree": 2, "decided": 4})
        kinds = sorted((d["verdict"], d["outcome"]) for d in report["disagreements"])
        self.assertEqual(kinds, [("approve", "not_run"), ("decline", "ran")])

    def test_an_outcome_pairs_with_one_verdict_only_and_sessions_must_match(self):
        report = self.report([verdict(0, "approve"), verdict(60, "approve")], [outcome(30, "ran")])
        self.assertEqual(report["matrix"]["approve"], {"ran": 1, "ran_failed": 0, "not_run": 1})
        report = self.report([verdict(0, "approve", session="s1")], [outcome(30, "ran", session="s2")])
        self.assertEqual(report["matrix"]["approve"]["not_run"], 1)
        self.assertEqual(report["unprompted"], 1)

    def test_an_outcome_before_the_prompt_or_long_after_it_does_not_pair(self):
        report = self.report([verdict(100, "approve")], [outcome(50, "ran")])
        self.assertEqual(report["matrix"]["approve"]["not_run"], 1)
        report = self.report([verdict(0, "approve")], [outcome(3 * 3600, "ran")])
        self.assertEqual(report["matrix"]["approve"]["not_run"], 1)

    def test_recent_verdicts_are_pending_not_counted_as_not_run(self):
        recent = {"ts": (NOW - datetime.timedelta(seconds=60)).isoformat(), "rule": "r", "verdict": "approve",
                  "command_sha256": "z", "session_id": "s1", "failed_checks": []}
        report = ca.build_report([recent], [], now=NOW)
        self.assertEqual(report["pending"], 1)
        self.assertEqual(report["matrix"]["approve"]["not_run"], 0)

    def test_days_filter_and_missing_data(self):
        old = verdict(-10 * 86400, "approve")
        report = self.report([old], [], days=7)
        self.assertEqual(sum(sum(row.values()) for row in report["matrix"].values()), 0)
        empty = self.report([], [])
        self.assertEqual(empty["agreement"], {"agree": 0, "decided": 0})
        self.assertIn("No verdicts", ca.format_report(empty))

    def test_a_verdict_without_a_session_cannot_be_paired(self):
        report = self.report([verdict(0, "approve", session=None)], [outcome(5, "ran")])
        self.assertEqual(report["matrix"]["approve"]["not_run"], 1)

    def test_bad_lines_and_rotated_files_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.jsonl"
            Path(str(path) + ".1").write_text(json.dumps({"n": 1}) + "\n")
            path.write_text("not json\n" + json.dumps({"n": 2}) + "\n[1]\n")
            self.assertEqual(ca.read_jsonl(path), [{"n": 1}, {"n": 2}])
            self.assertEqual(ca.read_jsonl(Path(tmp) / "absent.jsonl"), [])

    def test_the_text_report_names_the_disagreements_and_never_the_command(self):
        text = ca.format_report(self.report([verdict(0, "decline", reason_text="looked risky")], [outcome(5, "ran")]))
        self.assertIn("decline", text)
        self.assertIn("looked risky", text)
        self.assertIn("claude-workflow-commit", text)
        self.assertNotIn("d1", text.replace("disagreement", ""))


class ReportCommandTests(HookCase):
    def test_report_flag_prints_a_summary_and_does_not_read_stdin_or_decide(self):
        self.run_hook({"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": COMMAND},
                       "cwd": str(self.base), "session_id": "sess-1"})
        self.run_hook(self.post())
        r = self.run_hook(args=("--report",), stdin="")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("verdicts", r.stdout.lower())
        r = self.run_hook(args=("--report", "--days", "3"), stdin="")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_report_with_no_log_says_so(self):
        r = self.run_hook(args=("--report",), stdin="")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No verdicts", r.stdout)


if __name__ == "__main__":
    unittest.main()
