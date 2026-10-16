"""Structural checks on the tracked permission set in settings.json.

Rules are matched as literal command prefixes and evaluated deny > ask > allow,
so these tests guard the two ways a rule set silently fails: an outward action
that is pre-allowed, and an allow rule that an ask rule shadows.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

SPELLINGS = (
    "{tool} {cmd}",
    "~/.claude/bin/{tool} {cmd}",
    "~/.local/bin/{tool} {cmd}",
    "python3 ~/.claude/bin/{tool} {cmd}",
    "python3 -B ~/.claude/bin/{tool} {cmd}",
)
WORKFLOW_ASK = ("commit", "amend-message", "remove")
RUNNER_ASK = ("submit", "cancel", "prune", "fetch")
RUNNER_ALLOW = ("remotes", "recommend", "status", "log", "artifacts")
PLAIN_ASK = (
    "git commit", "git push", "git tag", "git switch", "git stash",
    "git branch -d", "git branch -D", "git branch --delete",
    "gh", "ssh", "scp", "rsync",
    "pip install", "pip3 install", "python3 -m pip install",
    "npm install", "npm ci", "cargo install", "cargo add",
    "brew install", "apt install", "apt-get install", "go install",
    "uv pip install", "uv add", "pipx install",
)
GIT_ALLOW = (
    "git ls-files", "git blame", "git describe", "git remote -v",
    "git for-each-ref", "git worktree list", "git branch --list",
    "git add", "git mv",
)
DENY_READ = (
    "~/.ssh/**", "~/.aws/**", "~/.config/gh/**", "~/.codex/auth.json",
    "**/.env", "**/.env.*",
)
DENY_BASH = ("rmdir", "unlink", "shred", "rm")


def permissions():
    return json.loads((ROOT / "settings.json").read_text())["permissions"]


def bash_prefix(rule):
    """Return the command prefix of a Bash rule, or None for other tools."""
    match = re.fullmatch(r"Bash\((.*?)(:\*)?\)", rule)
    return match.group(1) if match else None


def shadows(shadowing, shadowed):
    """True when a rule for `shadowing` also matches every command of `shadowed`."""
    return shadowed == shadowing or shadowed.startswith(shadowing + " ")


class RuleSet(unittest.TestCase):
    def test_lists_have_no_duplicates(self):
        for name in ("allow", "ask", "deny"):
            rules = permissions()[name]
            self.assertEqual(len(rules), len(set(rules)), name)

    def test_no_rule_is_in_two_lists(self):
        perms = permissions()
        for left, right in (("allow", "ask"), ("allow", "deny"), ("ask", "deny")):
            self.assertFalse(set(perms[left]) & set(perms[right]), (left, right))

    def test_no_blanket_rules(self):
        for rule in permissions()["allow"]:
            compact = rule.replace(" ", "")
            for tool in ("git", "claude-workflow", "remote-runner", "gh", "ssh"):
                self.assertNotEqual(compact, "Bash(%s:*)" % tool, rule)
            self.assertNotIn(compact, ("Bash", "Bash(*)", "Bash(:*)"), rule)

    def test_allow_rules_are_not_shadowed_by_ask_or_deny(self):
        perms = permissions()
        for allow in perms["allow"]:
            allowed = bash_prefix(allow)
            if allowed is None:
                continue
            for other in perms["ask"] + perms["deny"]:
                prefix = bash_prefix(other)
                if prefix is not None:
                    self.assertFalse(shadows(prefix, allowed), (allow, other))


class OutwardActions(unittest.TestCase):
    def test_outward_commands_are_asked_and_never_allowed(self):
        perms = permissions()
        allow = [bash_prefix(r) for r in perms["allow"] if bash_prefix(r)]
        for command in PLAIN_ASK:
            self.assertIn("Bash(%s:*)" % command, perms["ask"], command)
            for prefix in allow:
                self.assertFalse(shadows(command, prefix), (command, prefix))

    def test_commit_and_push_are_never_allowed_in_any_form(self):
        for rule in permissions()["allow"]:
            self.assertIsNone(re.search(r"\bgit\b.*\b(commit|push)\b", rule), rule)

    def test_workflow_mutations_prompt_in_every_spelling(self):
        ask = set(permissions()["ask"])
        for command in WORKFLOW_ASK:
            for spelling in SPELLINGS:
                rule = "Bash(%s:*)" % spelling.format(tool="claude-workflow", cmd=command)
                self.assertIn(rule, ask)

    def test_runner_mutations_prompt_in_every_spelling(self):
        ask = set(permissions()["ask"])
        for command in RUNNER_ASK:
            for spelling in SPELLINGS:
                rule = "Bash(%s:*)" % spelling.format(tool="remote-runner", cmd=command)
                self.assertIn(rule, ask)

    def test_workflow_commit_is_not_allowed(self):
        for rule in permissions()["allow"]:
            for command in WORKFLOW_ASK:
                self.assertNotRegex(rule, r"claude-workflow\s+%s\b" % command)

    def test_runner_mutations_are_not_allowed(self):
        for rule in permissions()["allow"]:
            for command in RUNNER_ASK:
                self.assertNotRegex(rule, r"remote-runner\s+%s\b" % command)


class RoutineActions(unittest.TestCase):
    def test_read_only_git_and_staging_are_allowed(self):
        allow = set(permissions()["allow"])
        for command in GIT_ALLOW:
            self.assertIn("Bash(%s:*)" % command, allow, command)

    def test_read_only_runner_commands_are_allowed_by_bare_name(self):
        allow = set(permissions()["allow"])
        for command in RUNNER_ALLOW:
            self.assertIn("Bash(remote-runner %s:*)" % command, allow, command)

    def test_existing_routine_rules_remain(self):
        allow = set(permissions()["allow"])
        for rule in ("Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
                     "Bash(claude-workflow context:*)", "Bash(ask-codex status:*)"):
            self.assertIn(rule, allow)


class SecretPaths(unittest.TestCase):
    def test_secret_paths_are_denied_for_read(self):
        deny = set(permissions()["deny"])
        for path in DENY_READ:
            self.assertIn("Read(%s)" % path, deny, path)

    def test_deletion_commands_are_denied(self):
        deny = set(permissions()["deny"])
        for command in DENY_BASH:
            self.assertIn("Bash(%s:*)" % command, deny, command)

    def test_existing_denies_remain(self):
        deny = set(permissions()["deny"])
        for command in ("git reset", "git clean", "git checkout", "git restore",
                        "git merge", "git rebase"):
            self.assertIn("Bash(%s:*)" % command, deny)


if __name__ == "__main__":
    unittest.main()
