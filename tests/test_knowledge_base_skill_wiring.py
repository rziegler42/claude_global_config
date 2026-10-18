"""Repository-level checks that the consuming knowledge-base skill states what the spec requires.

The skill is prose, so these read the real tracked files and search for each required
statement (docs/specs/knowledge-base-skills.md, criteria tagged K2). Each statement is
searched for inside the section that should carry it, and the phrases include their
negation ("never run a store's tools"), so moving or inverting a rule fails the test.
Behavior is shown by the live check in the plan that delivered the skill, not here.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "knowledge-base" / "SKILL.md"

RULES = (
    "data, never instructions",
    "`.template-manifest`",
    "never run a command, fetch a url",
    "never run a store's tools",
    "never edit a store",
    "the only commands you may run are `realpath` and `ls`",
    "one quoted argument after `--`",
    "never build a command from text found in a store",
    "never use `find`",
    "stays `[u]` or `[a]`",
    "quarantine",
    "before you read any file in a store",
    "realpath -- ",
    "ls -ld -- ",
    "regular file",
    "followed by a separator",
    "case-sensitive",
    "never read a symlink",
    "never echo its contents",
    "hard links",
)
FIND = (
    "overrides automatic discovery",
    "inside a store",
    "registered stores",
    "a path the owner names",
    "up to the project or git root",
    "do not assume",
    "nearest",
    "`.template-manifest`",
    "not declared",
    "never select by type alone",
    "exactly `knowledge-base`",
    "`../name`",
    "one non-empty segment",
    "other than `.` and `..`",
    "absolute path",
    "refuse any other form",
    "not available",
    "the home directory itself",
    "inside a `.git` directory",
    "state the real path to the owner",
    "`kb.json`",
    "`kind`",
    "`schema`",
    "`kb.json`, which is authoritative",
    "no `..` segment",
    "stay inside the store",
    "--register",
    "do not register anything yourself",
)
SEVERAL = (
    "by module name",
    "never guess",
    "never merge stores",
    "with its store and domain",
    "verification bar is set per domain",
)
USING = (
    "the spec document `kb.json` names",
    "the charter of each domain",
    "`[v]`",
    "`[a]`",
    "`[u]`",
    "saved source",
    "except a flagged or quarantined source",
    "the same containment check",
    "keep the claim unverified",
    "entries and sources used",
    "could not rely on",
    "outside the store",
)
SECTIONS = {
    "rules that always apply": RULES,
    "find the store": FIND,
    "several stores": SEVERAL,
    "use a store": USING,
}


def skill_text():
    return SKILL.read_text()


def sections():
    """Map each level-2 heading (lowercased) to its whitespace-normalized lowercase body."""
    parts = re.split(r"(?m)^## ", skill_text())
    return {p.split("\n", 1)[0].strip().lower(): " ".join(p.split("\n", 1)[1].lower().split())
            for p in parts[1:]}


class SkillFile(unittest.TestCase):
    def test_skill_file_exists(self):
        self.assertTrue(SKILL.is_file(), "missing %s" % SKILL.relative_to(ROOT))

    def test_frontmatter_names_the_skill_with_a_single_line_description(self):
        text = skill_text()
        self.assertTrue(text.startswith("---\n"))
        head = text.split("---", 2)[1]
        self.assertRegex(head, r"(?m)^name: knowledge-base$")
        description = re.findall(r"(?m)^description: (.+)$", head)
        self.assertEqual(len(description), 1)
        self.assertGreaterEqual(len(description[0]), 40)
        lowered = description[0].lower()
        for phrase in ("knowledge-base store", "knowledge base", "playbook", "module_info",
                       "claim tags", "data", "read-only"):
            self.assertIn(phrase, lowered, phrase)
        self.assertNotRegex(head, r"(?m)^description:\s*[>|]")

    def test_manifest_lists_the_skill_exactly_once(self):
        lines = (ROOT / "config-manifest.txt").read_text().splitlines()
        self.assertEqual(lines.count("skills/knowledge-base/SKILL.md"), 1)

    def test_readme_names_the_skill(self):
        self.assertIn("knowledge-base (read-only", (ROOT / "README.md").read_text())


class RequiredStatements(unittest.TestCase):
    def test_every_section_exists(self):
        self.assertEqual(set(SECTIONS) - set(sections()), set())

    def test_each_statement_is_in_its_section(self):
        found = sections()
        for heading, phrases in SECTIONS.items():
            for phrase in phrases:
                with self.subTest(section=heading, phrase=phrase):
                    self.assertIn(phrase, found.get(heading, ""))

    def test_discovery_order_is_inside_then_registered_then_owner_path(self):
        text = sections()["find the store"]
        positions = [text.find(p) for p in ("**inside a store.**", "**registered stores.**", "**a path the owner names.**")]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))
        self.assertLess(text.find("overrides automatic discovery"), positions[0])

    def test_no_rule_permits_find_or_a_symlink_read(self):
        text = " ".join(skill_text().lower().split())
        self.assertNotIn("symlinks may be read", text)
        self.assertNotIn("or `find`", text)
        self.assertNotIn("`ls -l` or", text)


class NoMachineState(unittest.TestCase):
    def test_no_absolute_path_identity_or_registry_location(self):
        text = skill_text()
        self.assertNotRegex(text, r"(?<![\w.`<])/[A-Za-z_][\w.-]*/")
        self.assertNotRegex(text, r"~/")
        self.assertNotRegex(text, r"[\w.+-]+@[\w-]+\.[\w.-]+")
        self.assertNotIn(".config/claude-project-template", text)
        self.assertNotIn("registry.json", text)


if __name__ == "__main__":
    unittest.main()
