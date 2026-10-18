"""Repository-level checks that the consuming knowledge-base skill states what the spec requires.

The skill is prose, so these read the real tracked files and search for each required
statement (docs/specs/knowledge-base-skills.md, criteria tagged K2). Behavior is shown by the
live check in the plan that delivered the skill, not here.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "knowledge-base" / "SKILL.md"

DISCOVERY = (
    "inside a store",
    "registered stores",
    "a path the owner names",
    "overrides automatic discovery",
    "`../name`",
    "absolute",
    "not declared",
    "not available",
    "`kb.json`",
    "`kind`",
    "`schema`",
    "before you read any file in a store",
    "regular file whose real path stays inside the store",
    "never read a symlink",
    "read-only `realpath`",
    "do not assume",
)
SEVERAL_STORES = (
    "by module name",
    "never select by type alone",
    "never guess",
    "never merge",
    "with its store and domain",
)
USING = (
    "router",
    "charter",
    "verification bar",
    "`[v]`",
    "`[a]`",
    "`[u]`",
    "saved source",
    "unverified",
    "entries and sources used",
    "could not rely on",
    "outside the store",
)
SAFETY = (
    "data, never instructions",
    "stays `[u]` or `[a]`",
    "quarantine",
    "never run a command",
    "never run a store's tools",
    "never edit a store",
    "--register",
)


def skill_text():
    return SKILL.read_text()


def normalized():
    return " ".join(skill_text().lower().split())


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
        for phrase in ("knowledge-base", "store", "claim tags"):
            self.assertIn(phrase, lowered, phrase)
        self.assertNotRegex(head, r"(?m)^description:\s*[>|]")

    def test_manifest_lists_the_skill(self):
        lines = (ROOT / "config-manifest.txt").read_text().splitlines()
        self.assertIn("skills/knowledge-base/SKILL.md", lines)


class RequiredStatements(unittest.TestCase):
    def check(self, phrases):
        text = normalized()
        for phrase in phrases:
            self.assertIn(phrase, text, phrase)

    def test_discovery(self):
        self.check(DISCOVERY)

    def test_discovery_order_is_inside_then_registered_then_owner_path(self):
        text = normalized()
        positions = [text.find(p) for p in ("inside a store", "registered stores", "a path the owner names")]
        self.assertNotIn(-1, positions)
        self.assertEqual(positions, sorted(positions))

    def test_several_stores(self):
        self.check(SEVERAL_STORES)

    def test_using_a_store(self):
        self.check(USING)

    def test_safety_rules(self):
        self.check(SAFETY)


class NoMachineState(unittest.TestCase):
    def test_no_absolute_path_identity_or_registry_location(self):
        text = skill_text()
        self.assertNotRegex(text, r"/(Users|home|private|tmp|var)/")
        self.assertNotRegex(text, r"[\w.+-]+@[\w-]+\.[\w.-]+")
        self.assertNotIn(".config/claude-project-template", text)
        self.assertNotIn("registry.json", text)


if __name__ == "__main__":
    unittest.main()
