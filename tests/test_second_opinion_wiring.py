"""Repository-level checks that the second-opinion helper is wired in safely.

These read the real tracked files (manifest, settings, installer), not a
throwaway tree: they guard the owner-approval gates and the install wiring.
"""
import json
from pathlib import Path
import re
import stat
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATED = ("extend", "reset", "prune", "archive")
OPEN = ("review-plan", "review-spec", "review-roadmap", "review-adr", "decide", "status", "models", "init")
SPELLINGS = (
    "ask-codex {cmd}",
    "~/.claude/bin/ask-codex {cmd}",
    "~/.local/bin/ask-codex {cmd}",
    "python3 ~/.claude/bin/ask-codex {cmd}",
    "python3 -B ~/.claude/bin/ask-codex {cmd}",
)
MANIFEST_PATHS = (
    "bin/ask-codex",
    "ask-codex/config.json",
    "ask-codex/kinds/plan-review/kind.json",
    "ask-codex/kinds/plan-review/prompt.md",
    "ask-codex/kinds/plan-review/schema.json",
    "ask-codex/kinds/spec-review/kind.json",
    "ask-codex/kinds/spec-review/prompt.md",
    "ask-codex/kinds/spec-review/schema.json",
    "ask-codex/kinds/roadmap-review/kind.json",
    "ask-codex/kinds/roadmap-review/prompt.md",
    "ask-codex/kinds/roadmap-review/schema.json",
    "ask-codex/kinds/adr-review/kind.json",
    "ask-codex/kinds/adr-review/prompt.md",
    "ask-codex/kinds/adr-review/schema.json",
)
# What each document kind's prompt must ask the reviewer to judge.
KIND_CRITERIA = {
    "spec-review": ("scope", "non-goals", "acceptance criteria", "testable", "adr",
                    "implementation sequencing", "work log"),
    "roadmap-review": ("promotion trigger", "dependencies", "plan-boundary", "file lists",
                       "authoriz", "adr", "status"),
    "adr-review": ("alternatives", "consequences", "supersede", "contradict", "context",
                   "authorization"),
}


def manifest():
    lines = (ROOT / "config-manifest.txt").read_text().splitlines()
    return [line for line in lines if line and not line.startswith("#")]


def permissions():
    return json.loads((ROOT / "settings.json").read_text())["permissions"]


class ManifestAndInstaller(unittest.TestCase):
    def test_manifest_lists_every_ask_codex_file(self):
        listed = manifest()
        for path in MANIFEST_PATHS:
            self.assertIn(path, listed)
            self.assertTrue((ROOT / path).is_file(), path)

    def test_document_kinds_are_complete_and_share_the_plan_schema(self):
        kinds = ROOT / "ask-codex" / "kinds"
        plan_schema = json.loads((kinds / "plan-review" / "schema.json").read_text())
        for name, phrases in KIND_CRITERIA.items():
            with self.subTest(kind=name):
                meta = json.loads((kinds / name / "kind.json").read_text())
                self.assertEqual(meta["name"], name)
                self.assertEqual((meta["prompt"], meta["schema"]), ("prompt.md", "schema.json"))
                self.assertTrue(meta["uses_loop"] and meta["uses_ledger"])
                self.assertEqual(json.loads((kinds / name / "schema.json").read_text()), plan_schema)
                prompt = (kinds / name / "prompt.md").read_text()
                for placeholder in ("{{ROUND}}", "{{DOC_PATH}}", "{{LEDGER}}"):
                    self.assertIn(placeholder, prompt)
                self.assertNotIn("{{PLAN_PATH}}", prompt)
                lowered = prompt.lower()
                for phrase in ("read-only", "do not invent problems", "blocker", "reraises") + phrases:
                    self.assertIn(phrase, lowered, phrase)

    def test_helper_is_executable_with_shebang(self):
        path = ROOT / "bin" / "ask-codex"
        self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
        self.assertEqual(path.read_bytes()[:2], b"#!")

    def test_installer_links_the_helper(self):
        text = (ROOT / "install.py").read_text()
        match = re.search(r"^HELPERS = \((.*?)\)", text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertIn('"ask-codex"', match.group(1))

    def test_helper_resolves_its_tool_home_in_the_installed_layout(self):
        # bin/ask-codex finds ../ask-codex; installed ~/.claude has the same shape.
        text = (ROOT / "bin" / "ask-codex").read_text()
        self.assertIn('HERE.parent.parent / "ask-codex"', text)


class Permissions(unittest.TestCase):
    def test_owner_gated_commands_prompt_in_every_known_spelling(self):
        ask = set(permissions().get("ask", []))
        for command in GATED:
            for spelling in SPELLINGS:
                rule = "Bash(%s:*)" % spelling.format(cmd=command)
                self.assertIn(rule, ask)

    def test_gated_commands_are_never_pre_allowed(self):
        allow = permissions()["allow"]
        for rule in allow:
            for command in GATED:
                self.assertNotIn("ask-codex %s" % command, rule, rule)
        self.assertFalse(any(re.search(r"ask-codex\s*:\*|ask-codex \*", r) for r in allow))

    def test_routine_commands_are_allowed_by_bare_name(self):
        allow = set(permissions()["allow"])
        for command in OPEN:
            self.assertIn("Bash(ask-codex %s:*)" % command, allow)

    def test_no_blanket_allow_of_the_helper(self):
        for rule in permissions()["allow"]:
            self.assertNotEqual(rule.replace(" ", ""), "Bash(ask-codex:*)")


class Specs(unittest.TestCase):
    def test_plan_review_spec_points_to_the_document_review_spec(self):
        text = (ROOT / "docs" / "specs" / "second-opinion-plan-review.md").read_text()
        self.assertIn("second-opinion-document-review.md", text)


if __name__ == "__main__":
    unittest.main()
