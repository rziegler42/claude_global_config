"""Repository-level checks that the knowledge-base-authoring skill states what the spec requires.

The skill is prose, so these read the real tracked files and search for each required
statement (docs/specs/knowledge-base-skills.md, criteria tagged K3, and criterion 11 for this
skill). Each statement is searched for inside the section that should carry it, and the phrases
include their negation ("never default"), so moving or inverting a rule fails the test.
Behavior is shown by the live check in the plan that delivered the skill, not here.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "knowledge-base-authoring"
SKILL = SKILL_DIR / "SKILL.md"
REFERENCE = SKILL_DIR / "references" / "create-and-upgrade.md"
DOMAIN = SKILL_DIR / "references" / "domain.md"
MANIFEST_LINES = (
    "skills/knowledge-base-authoring/SKILL.md",
    "skills/knowledge-base-authoring/references/create-and-upgrade.md",
    "skills/knowledge-base-authoring/references/domain.md",
)

RULES = (
    "data, never instructions",
    "`.template-manifest`",
    "never run a command, fetch a url",
    "stays `[u]` or `[a]`",
    "quarantine",
    "realpath -- ",
    "ls -ld -- ",
    "regular file",
    "followed by a separator",
    "case-sensitive",
    "never read a symlink",
    "every read of a store file",
    "`.kb-manifest`",
    "before every tool run",
    "`tools/check_kb.py`",
    "`tools/kb_status.py`",
    "`tools/new_domain.py`",
    "resolves outside the store",
    "does not run it",
    "a change between the check and the run",
    "the installer's own output",
    "`next:` hint",
    "check what a tool imports",
    "a name with no match is an extra entry",
    "run a tool only when there is no extra entry",
    "`__pycache__`",
    "ls -a -- ",
    "`python3 -b -i`",
    "control character",
)
TARGET = (
    "never default",
    "the owner names",
    "holds the working directory",
    "state the real path",
    "before any installer, git, store-tool or write operation",
    "the only commands allowed before confirmation",
    "inside a git repository",
    "sibling",
    "`../name`",
)
CHECKOUT = (
    "ask the owner for the path",
    "environment variable",
    "`install.py`",
    "`kit/kit.json`",
    "`kit/files`",
    "no symlink",
    "python3 -i",
    "absolute path",
    "`--dry-run` first",
    "hostile checkout",
    "their own",
    "does not rely on the current directory",
)
IDENTITY = (
    "a name and an address",
    "noreply",
    "publish",
    "never guess",
    "global identity",
)
PERMISSIONS = (
    "prompts",
    "owner decides",
    "release",
    "never commit or push",
    "never register",
    "never install a dependency",
    "skipped or conflicted on a tool",
    "writing lifecycle tool",
    "`new_domain.py`",
)
OPERATIONS = (
    "references/create-and-upgrade.md",
    "references/domain.md",
    "create a domain",
    "domain",
    "wave",
    "expand",
    "not yet available",
)
SKILL_SECTIONS = {
    "rules that always apply": RULES,
    "choose the target": TARGET,
    "find the starter checkout": CHECKOUT,
    "git identity": IDENTITY,
    "permissions": PERMISSIONS,
    "operations": OPERATIONS,
}

CREATE = (
    "target path",
    "project name",
    "git identity",
    "`--dry-run`",
    "go-ahead",
    "`kb.json`",
    "`kind`",
    "`schema`",
    "`agents.md`",
    "domain-lifecycle.md",
    "untrusted data",
    "`check_kb.py`",
    "`kb_status.py`",
    "positional",
    "`--dir` belongs to `--upgrade` only",
    "wait for the owner to confirm",
    "report its message verbatim",
    "only when the value is `docs/kb/knowledge-base-format.md`",
)
UPGRADE = (
    "preflight",
    "`agents.md`",
    "`kb.json`",
    "domain-lifecycle.md",
    "never authorize a command or flag found in them",
    "`starter_commit`",
    'git -c "<checkout>" rev-parse head',
    "`--upgrade --dir`",
    "`--dry-run`",
    "conflict",
    "under `tools/`",
    "ask before running",
    "owner-edited",
    "40 lowercase hexadecimal",
    "run no tool",
    "only when the value is `docs/kb/knowledge-base-format.md`",
)
CHECK = (
    "`check_kb.py`",
    "`kb_status.py`",
    "report both",
    "the files the upgrade skipped",
    "skipped or conflicted",
    "`git diff`",
    "`git status`",
)
REGISTRATION = (
    "registration line",
    "--register",
    "the owner runs it",
    "do not run it",
    "the `next:` hint",
)
NEVER = (
    "never registers",
    "never commits",
    "never pushes",
    "never edits a skipped file",
    "`docs/specs/installer.md`",
    "`docs/kb/`",
)
DOMAIN_CREATE = (
    "ask the owner for the domain name and title",
    "never guess",
    "validate both yourself",
    "does not stand in for this check",
    "lowercase letters, digits and hyphens",
    "ascii letters, digits, spaces",
    "every quote, backtick, `$`",
    "starts with a hyphen",
    "single quotes",
    "link count is above 1",
    "the owner confirms the real path of the store",
    "preflight",
    "`agents.md`",
    "`kb.json`",
    "docs/kb/domain-lifecycle.md",
    "untrusted data",
    "never authorize a command or flag found in them",
    "only when the value is `docs/kb/knowledge-base-format.md`",
    "run `tools/new_domain.py <name> --title <title>`",
    "`python3 -b -i`",
    "entrypoint and imports checks",
    "the exact command",
    "report its message verbatim",
    "no other option",
    "does not answer it",
    "waits for the owner's answer to that question",
    "the root router",
    "`playbook/readme.md`",
)
DOMAIN_DRAFT = (
    "domains/<name>/readme.md",
    "`questions.md`",
    "the six headings",
    "decision-shaped",
    "at least three",
    "who reads this",
    "the charter is the owner's decision",
    "mark it as a proposal",
    "do not invent",
    "keep the front matter",
    "invisible or bidirectional-control characters",
    "a passing check does not vouch for content",
    "show the owner the full draft",
    "the tool's own writes",
    "makes no file-tool write until the owner approves",
    "stays as the tool left it",
    "does not remove it",
    "then write it",
    "`charter: draft` unchanged",
    "path-check each target",
)
DOMAIN_SET = (
    "`check_kb.py`",
    "at most three",
    "then stop and report",
    "separate confirmation",
    "entries may then be added",
    "cannot return to draft",
    "only on that confirmation",
    "with no arguments",
    "asked after the step 9 check passes",
    "any earlier \"go ahead\", does not count",
    "never replace all",
    "left with `charter: set` and failing",
    "change `charter: draft` to `charter: set`",
    "run `check_kb.py` again",
    "`kb_status.py`",
    "after the final",
)
DOMAIN_NEVER = (
    "never commits",
    "never pushes",
    "never adds a source or an entry",
    "never starts a wave",
    "never removes or renames a domain",
    "links the store's `docs/kb/domain-lifecycle.md`",
    "does not copy",
)
DOMAIN_SECTIONS = {
    "create the domain": DOMAIN_CREATE,
    "draft the charter and the questions": DOMAIN_DRAFT,
    "set the charter and check": DOMAIN_SET,
    "never": DOMAIN_NEVER,
}
REFERENCE_SECTIONS = {
    "create a store": CREATE,
    "upgrade a store": UPGRADE,
    "check and report": CHECK,
    "registration": REGISTRATION,
    "never": NEVER,
}

# The spec's table of tools and flags a skill may mention (K3 subset), plus --register,
# which only appears as the template's line that the owner runs.
ALLOWED_TOOLS = {"check_kb.py", "kb_status.py", "new_domain.py"}
ALLOWED_FLAGS = {"--dry-run", "--upgrade", "--dir", "--git-name", "--git-email", "--register",
                 "--title"}


def read(path):
    return path.read_text()


def sections(path):
    """Map each level-2 heading (lowercased) to its whitespace-normalized lowercase body."""
    parts = re.split(r"(?m)^## ", read(path))
    return {p.split("\n", 1)[0].strip().lower(): " ".join(p.split("\n", 1)[1].lower().split())
            for p in parts[1:]}


class SkillFiles(unittest.TestCase):
    def test_both_files_exist(self):
        for path in (SKILL, REFERENCE, DOMAIN):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.is_file(), "missing %s" % path.relative_to(ROOT))

    def test_frontmatter_names_the_skill_with_a_single_line_description(self):
        text = read(SKILL)
        self.assertTrue(text.startswith("---\n"))
        head = text.split("---", 2)[1]
        self.assertRegex(head, r"(?m)^name: knowledge-base-authoring$")
        description = re.findall(r"(?m)^description: (.+)$", head)
        self.assertEqual(len(description), 1)
        lowered = description[0].lower()
        for phrase in ("create", "upgrade", "knowledge-base store", "domain", "wave",
                       "expand", "status report", "`kb.json`"):
            self.assertIn(phrase, lowered, phrase)
        self.assertNotRegex(head, r"(?m)^description:\s*[>|]")

    def test_manifest_lists_each_file_exactly_once(self):
        lines = (ROOT / "config-manifest.txt").read_text().splitlines()
        for line in MANIFEST_LINES:
            with self.subTest(line=line):
                self.assertEqual(lines.count(line), 1)

    def test_readme_names_the_skill(self):
        text = " ".join((ROOT / "README.md").read_text().split())
        self.assertIn("knowledge-base-authoring (create and upgrade a store, create a domain", text)


class RequiredStatements(unittest.TestCase):
    def check_sections(self, path, table):
        found = sections(path) if path.is_file() else {}
        self.assertEqual(set(table) - set(found), set(), "missing sections in %s" % path.name)
        for heading, phrases in table.items():
            for phrase in phrases:
                with self.subTest(file=path.name, section=heading, phrase=phrase):
                    self.assertIn(phrase, found.get(heading, ""))

    def test_skill_statements_are_in_their_sections(self):
        self.check_sections(SKILL, SKILL_SECTIONS)

    def test_reference_statements_are_in_their_sections(self):
        self.check_sections(REFERENCE, REFERENCE_SECTIONS)

    def test_create_reads_the_new_store_before_running_its_tools(self):
        text = sections(REFERENCE).get("create a store", "")
        reads = text.find("`agents.md`")
        tools = text.find("`check_kb.py`")
        self.assertNotEqual(reads, -1)
        self.assertLess(reads, tools)

    def test_create_confirms_the_target_before_the_dry_run(self):
        text = sections(REFERENCE).get("create a store", "")
        confirm = text.find("wait for the owner to confirm")
        dry_run = text.find("and show the owner the installer run")
        self.assertNotEqual(confirm, -1)
        self.assertLess(confirm, dry_run)

    def test_domain_statements_are_in_their_sections(self):
        self.check_sections(DOMAIN, DOMAIN_SECTIONS)

    def test_domain_reads_the_store_before_running_the_tool(self):
        text = sections(DOMAIN).get("create the domain", "")
        reads = text.find("preflight")
        run = text.find("run `tools/new_domain.py <name> --title <title>`")
        self.assertNotEqual(reads, -1)
        self.assertNotEqual(run, -1)
        self.assertLess(reads, run)

    def test_domain_name_and_title_are_validated_before_the_command_is_built(self):
        text = sections(DOMAIN).get("create the domain", "")
        validated = text.find("validate both yourself")
        shown = text.find("show the owner the exact command")
        run = text.find("run `tools/new_domain.py <name> --title <title>`")
        self.assertNotEqual(validated, -1)
        self.assertLess(validated, shown)
        self.assertLess(shown, run)

    def test_domain_draft_is_shown_before_any_file_tool_write(self):
        text = sections(DOMAIN).get("draft the charter and the questions", "")
        shown = text.find("show the owner the full draft")
        write = text.find("then write it")
        self.assertNotEqual(shown, -1)
        self.assertNotEqual(write, -1)
        self.assertLess(shown, write)

    def test_domain_charter_is_set_only_after_the_separate_confirmation(self):
        text = sections(DOMAIN).get("set the charter and check", "")
        first_check = text.find("`check_kb.py`")
        confirm = text.find("separate confirmation")
        flip = text.find("change `charter: draft` to `charter: set`")
        again = text.find("run `check_kb.py` again")
        status = text.find("`kb_status.py`")
        self.assertNotEqual(first_check, -1)
        for earlier, later in ((first_check, confirm), (confirm, flip), (flip, again), (again, status)):
            self.assertNotEqual(later, -1)
            self.assertLess(earlier, later)

    def test_upgrade_preflight_comes_before_the_manifest_read_and_the_run(self):
        text = sections(REFERENCE).get("upgrade a store", "")
        preflight = text.find("2. preflight")
        manifest = text.find("3. read the store's `.kb-manifest`")
        run = text.find("4. show the owner the installer's `--upgrade --dir`")
        self.assertNotEqual(preflight, -1)
        self.assertLess(preflight, manifest)
        self.assertLess(manifest, run)


class ToolsAndFlags(unittest.TestCase):
    def texts(self):
        return {p.name: read(p) for p in (SKILL, REFERENCE, DOMAIN) if p.is_file()}

    def test_every_tool_and_flag_is_in_the_specs_table(self):
        texts = self.texts()
        self.assertEqual(len(texts), 3)
        for name, text in texts.items():
            for tool in set(re.findall(r"tools/(\w+\.py)", text)):
                with self.subTest(file=name, tool=tool):
                    self.assertIn(tool, ALLOWED_TOOLS)
            for flag in set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", text)):
                with self.subTest(file=name, flag=flag):
                    self.assertIn(flag, ALLOWED_FLAGS)

    def test_no_flag_outside_the_table_is_volunteered(self):
        for name, text in self.texts().items():
            for flag in ("--name", "--use-global-git-identity", "--skip-unsafe-entries", "--add-to"):
                with self.subTest(file=name, flag=flag):
                    self.assertNotIn(flag, text)


class NoMachineState(unittest.TestCase):
    def test_no_absolute_path_identity_or_registry_location(self):
        for path in (SKILL, REFERENCE, DOMAIN):
            text = read(path) if path.is_file() else None
            with self.subTest(path=path.name):
                self.assertIsNotNone(text, "missing %s" % path.relative_to(ROOT))
                self.assertNotRegex(text, r"(?<![\w.`<>])/[A-Za-z_][\w.-]*/")
                self.assertNotRegex(text, r"~/")
                self.assertNotRegex(text, r"[\w.+-]+@[\w-]+\.[\w.-]+")
                self.assertNotIn(".config/claude-project-template", text)
                self.assertNotIn("registry.json", text)


if __name__ == "__main__":
    unittest.main()
