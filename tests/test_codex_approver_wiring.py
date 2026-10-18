"""Wiring checks for the Codex approver: settings registration, manifest, ignore rules, docs.

Run from the repository root with:  python3 -B -m unittest discover -s tests
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = (
    "/bin/sh -c 'set -f; IFS=:; for d in $PATH; do case \"$d\" in /*) if [ -x \"$d/python3\" ]; then "
    "exec \"$d/python3\" -B \"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/codex_approver.py\"; fi;; esac; done; exit 0'"
)


def settings():
    return json.loads((ROOT / "settings.json").read_text())


def manifest():
    lines = (ROOT / "config-manifest.txt").read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


class SettingsWiringTests(unittest.TestCase):
    def test_exactly_one_permission_request_hook_for_bash(self):
        hooks = settings()["hooks"]
        self.assertEqual(sorted(hooks), ["PermissionRequest", "PostToolUse", "PostToolUseFailure"])
        (group,) = hooks["PermissionRequest"]
        self.assertEqual(group["matcher"], "Bash")
        (hook,) = group["hooks"]
        self.assertEqual((hook["type"], hook["command"]), ("command", COMMAND))
        self.assertNotIn("if", hook)

    def test_outcome_hooks_run_only_for_the_covered_commands(self):
        """PostToolUse(Failure) records whether a covered command ran; `if` stops it spawning for any other Bash call."""
        spellings = ("claude-workflow", "~/.claude/bin/claude-workflow", "~/.local/bin/claude-workflow",
                     "python3 ~/.claude/bin/claude-workflow", "python3 -B ~/.claude/bin/claude-workflow")
        expected = {"Bash(%s %s:*)" % (spelling, sub) for spelling in spellings for sub in ("commit", "remove")}
        expected.add("Bash(git push:*)")
        expected |= {"Bash(%s archive:*)" % spelling for spelling in (
            "ask-codex", "~/.claude/bin/ask-codex", "~/.local/bin/ask-codex",
            "python3 ~/.claude/bin/ask-codex", "python3 -B ~/.claude/bin/ask-codex")}
        runner = ("remote-runner", "~/.claude/bin/remote-runner", "~/.local/bin/remote-runner",
                  "python3 ~/.claude/bin/remote-runner", "python3 -B ~/.claude/bin/remote-runner")
        expected |= {"Bash(%s %s:*)" % (spelling, sub) for spelling in runner
                     for sub in ("submit", "fetch", "cancel", "prune")}
        asked = {rule for rule in settings()["permissions"]["ask"] if rule in expected}
        self.assertEqual(asked, expected, "the filters must be the same patterns the ask rules use")
        for event in ("PostToolUse", "PostToolUseFailure"):
            with self.subTest(event=event):
                (group,) = settings()["hooks"][event]
                self.assertEqual(group["matcher"], "Bash")
                self.assertEqual({h["if"] for h in group["hooks"]}, expected)
                self.assertEqual(len(group["hooks"]), len(expected), "one handler per pattern, no duplicates")
                for hook in group["hooks"]:
                    self.assertEqual((hook["type"], hook["command"]), ("command", COMMAND))
                    self.assertIsInstance(hook["timeout"], int)
                    self.assertLessEqual(hook["timeout"], 10)

    def test_hook_timeout_covers_codex_with_margin_and_stays_short(self):
        (hook,) = settings()["hooks"]["PermissionRequest"][0]["hooks"]
        config = json.loads((ROOT / "codex-approver" / "config.json").read_text())
        self.assertIsInstance(hook["timeout"], int)
        self.assertGreaterEqual(hook["timeout"], config["codex_timeout_seconds"] + 5)
        self.assertLessEqual(hook["timeout"], 60)

    def test_launch_skips_empty_and_relative_path_entries(self):
        (hook,) = settings()["hooks"]["PermissionRequest"][0]["hooks"]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            planted = base / "repo"
            planted.mkdir()
            marker = base / "planted-ran"
            (planted / "python3").write_text('#!/bin/sh\necho planted > "%s"\n' % marker)
            (planted / "python3").chmod(0o755)
            real = base / "realbin"
            real.mkdir()
            record = base / "real-args"
            (real / "python3").write_text('#!/bin/sh\necho "$@" > "%s"\n' % record)
            (real / "python3").chmod(0o755)
            config = base / "claudehome"
            for path_value in (":" + str(real), ".:" + str(real), "rel:" + str(real)):
                if record.exists():
                    record.unlink()
                r = subprocess.run(hook["command"], shell=True, cwd=planted, input="{}", capture_output=True,
                                   text=True, timeout=30, env={"PATH": path_value, "HOME": tmp,
                                                               "CLAUDE_CONFIG_DIR": str(config)})
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertFalse(marker.exists(), "planted python3 ran via PATH entry " + path_value)
                self.assertEqual(record.read_text().split(), ["-B", str(config / "hooks" / "codex_approver.py")])

    def test_launch_does_not_expand_glob_characters_in_path_entries(self):
        (hook,) = settings()["hooks"]["PermissionRequest"][0]["hooks"]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "globXdir"
            target.mkdir()
            marker = base / "glob-ran"
            (target / "python3").write_text('#!/bin/sh\necho x > "%s"\n' % marker)
            (target / "python3").chmod(0o755)
            for pattern in ("glob*", "glob?dir", "glob[X]dir"):
                r = subprocess.run(hook["command"], shell=True, input="{}", capture_output=True, text=True,
                                   timeout=30, env={"PATH": str(base / pattern), "HOME": tmp})
                self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
                self.assertFalse(marker.exists(), "glob in PATH expanded: " + pattern)

    def test_launch_with_no_usable_python3_makes_no_decision(self):
        (hook,) = settings()["hooks"]["PermissionRequest"][0]["hooks"]
        r = subprocess.run(hook["command"], shell=True, input="{}", capture_output=True, text=True, timeout=30,
                           env={"PATH": "relative:", "HOME": "/nonexistent"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_shipped_config_delegates_the_commit_and_archive_rules_and_nothing_else(self):
        # ADR 0005 and ADR 0006. Revoking the authority means mode "advise" with an empty list (also valid); never any other rule.
        config = json.loads((ROOT / "codex-approver" / "config.json").read_text())
        self.assertEqual((config["mode"], config["delegate"]),
                         ("delegate", ["claude-workflow-commit", "ask-codex-archive"]))

    def test_the_hook_is_not_a_permission_rule_and_no_rule_was_relaxed(self):
        permissions = settings()["permissions"]
        # The hook is never a Bash permission rule; the only permission entries naming its files are the `ask`
        # rules that make any edit of the approver's code, rules or config (including the delegate switch) prompt.
        named = {(tier, rule) for tier in ("allow", "ask", "deny") for rule in permissions.get(tier, [])
                 if "codex_approver" in rule or "codex-approver" in rule}
        self.assertEqual(named, {("ask", "Edit(%s)" % path)
                                 for path in ("~/.claude/codex-approver/**", "~/.claude/hooks/codex_approver.py")})
        # Claude Code matches file permissions with Edit rules only (they cover every file-editing tool); a Write
        # rule is reported at startup as never matching.
        protected = {rule for rule in permissions["ask"] if rule.startswith(("Edit(", "Write("))}
        self.assertEqual(protected, {"Edit(%s)" % path for path in (
            "~/.claude/codex-approver/**", "~/.claude/hooks/codex_approver.py", "~/.claude/bin/claude-workflow")})
        for command in ("commit", "remove"):
            self.assertTrue(any(rule.endswith("claude-workflow %s:*)" % command) for rule in permissions["ask"]))
            self.assertFalse(any("claude-workflow %s" % command in rule for rule in permissions["allow"]))


class ManifestTests(unittest.TestCase):
    def test_hook_and_data_files_are_listed_and_exist(self):
        listed = set(manifest())
        data = {str(p.relative_to(ROOT)) for p in (ROOT / "codex-approver").rglob("*")
                if p.is_file() and "log" not in p.relative_to(ROOT / "codex-approver").parts}
        self.assertIn("hooks/codex_approver.py", listed)
        self.assertTrue(data <= listed, sorted(data - listed))
        for name in ("config.json", "rubric.md", "verdict.schema.json"):
            self.assertIn("codex-approver/" + name, listed)
        for path in listed:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_runtime_log_is_never_listed_or_tracked(self):
        self.assertFalse([p for p in manifest() if "/log/" in p or p.endswith(".jsonl")])
        self.assertIn("/codex-approver/log/", (ROOT / ".gitignore").read_text().splitlines())

    def test_install_dry_run_plans_the_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLAUDE_CONFIG_DIR=tmp, HOME=tmp)
            r = subprocess.run([sys.executable, "-B", str(ROOT / "install.py"), "--dry-run", "--no-link-bin"],
                               capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("codex_approver.py", r.stdout)
        self.assertIn("codex-approver/rubric.md", r.stdout)


class RubricTests(unittest.TestCase):
    def test_every_review_check_is_defined_in_its_rubric_section(self):
        rubric = (ROOT / "codex-approver" / "rubric.md").read_text()
        for path in sorted((ROOT / "codex-approver" / "rules").glob("*.json")):
            rule = json.loads(path.read_text())
            marker = "## rubric: " + rule["rubric"]
            self.assertIn(marker, rubric, path.name)
            section = rubric.split(marker, 1)[1].split("\n## rubric: ")[0]
            for check in rule["review_checks"]:
                self.assertIn("`%s`" % check, section, "%s: %s is not defined in the rubric" % (path.name, check))

    def test_the_commit_rubric_judges_the_change_itself_not_only_the_message(self):
        rubric = (ROOT / "codex-approver" / "rubric.md").read_text()
        section = rubric.split("## rubric: commit", 1)[1].split("\n## rubric: ")[0]
        self.assertIn("change_is_safe_in_itself", section)
        self.assertIn("does not make a harmful change safe", section)


class DocumentationTests(unittest.TestCase):
    def test_adr_is_indexed_and_readme_documents_the_feature(self):
        adr = ROOT / "docs" / "decisions" / "0004-codex-approver-advice-only.md"
        self.assertTrue(adr.is_file())
        self.assertIn("0004-codex-approver-advice-only.md", (ROOT / "docs" / "decisions" / "README.md").read_text())
        readme = (ROOT / "README.md").read_text()
        self.assertIn("## Codex approver", readme)
        self.assertIn("hooks/codex_approver.py", readme)

    def test_spec_records_acceptance_of_increment_one(self):
        spec = (ROOT / "docs" / "specs" / "codex-approver.md").read_text()
        self.assertIn("Status: Accepted", spec)
        self.assertNotIn("paths exactly the staged set", spec)
        self.assertNotIn("identical command that was previewed", spec)


if __name__ == "__main__":
    unittest.main()
