"""Tests for the path-aware secret scan of the commit collector (plan: docs/plans/next.md, increment G).

Run from the repository root with:  python3 -B -m unittest discover -s tests -p 'test_codex_approver_pathscan.py'
"""
import unittest

from test_codex_approver_rules import FAKE_AWS_KEY, RuleCase, ca

NPM_LINES = (
    '    "node_modules/@rolldown/binding-openharmony-arm64": {\n'
    '      "resolved": "https://registry.npmjs.org/@rolldown/binding-linux-arm64-musl/-/binding-linux-arm64-musl-1.2.14.tgz",\n'
    '      "@typescript/typescript-linux-mips64el": "7.0.2",\n')
FIXTURE = 'def test_x():\n    send(ws, type="resume", token="doesnotexist1234567890")\n'
GITHUB_TOKEN = "ghp_" + "a1B2c3D4e5" * 4


class ScanOptionTests(unittest.TestCase):
    def test_entropy_can_be_skipped_but_patterns_still_run(self):
        self.assertEqual(ca.secret_kind("+" + NPM_LINES), "high_entropy")
        self.assertIsNone(ca.secret_kind("+" + NPM_LINES, entropy=False))
        self.assertEqual(ca.secret_kind("+k = " + GITHUB_TOKEN, entropy=False), "pattern")

    def test_generic_assignments_can_be_relaxed_but_specific_patterns_run(self):
        self.assertEqual(ca.secret_kind("+" + FIXTURE), "pattern")
        self.assertIsNone(ca.secret_kind("+" + FIXTURE, relaxed=True))
        for line in ("+k = " + GITHUB_TOKEN, "+a = " + FAKE_AWS_KEY, "+client_secret = abcdefgh12345678",
                     "+u = https://user:pass@example.invalid/x", "+Authorization: Bearer abcdefghijklmnop1234"):
            with self.subTest(line=line):
                self.assertEqual(ca.secret_kind(line, relaxed=True), "pattern")

    def test_path_policy(self):
        self.assertEqual(ca.scan_options("web/package-lock.json"), {"entropy": False, "relaxed": False})
        self.assertEqual(ca.scan_options("Cargo.lock"), {"entropy": False, "relaxed": False})
        self.assertEqual(ca.scan_options("tests/web/test_x.py"), {"entropy": True, "relaxed": True})
        self.assertEqual(ca.scan_options("pkg/__tests__/a.js"), {"entropy": True, "relaxed": True})
        for path in ("src/tests.py", "src/test_x.py", "src/attests/x.py", "package-lock.json.bak", "src/mylock.json",
                     "docs/package-lock.json/readme.md"):
            with self.subTest(path=path):
                self.assertEqual(ca.scan_options(path), {"entropy": True, "relaxed": False})


class CommitScanTests(RuleCase):
    def commit_fails(self, path, text):
        full = self.repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text)
        return "no_secret_lines" in self.analyze(self.commit_command(path))["failed"]

    def test_a_lockfile_with_package_names_is_clean_but_a_token_in_it_is_not(self):
        self.assertFalse(self.commit_fails("web/package-lock.json", NPM_LINES))
        self.assertTrue(self.commit_fails("web/package-lock.json", NPM_LINES + "  k = " + GITHUB_TOKEN + "\n"))
        self.assertTrue(self.commit_fails("web/notes.txt", NPM_LINES))

    def test_a_test_fixture_is_clean_but_a_real_shaped_token_is_not(self):
        self.assertFalse(self.commit_fails("tests/web/test_ws.py", FIXTURE))
        self.assertTrue(self.commit_fails("tests/web/test_ws2.py", "x = " + GITHUB_TOKEN + "\n"))
        self.assertTrue(self.commit_fails("tests/web/test_ws3.py", "x = " + FAKE_AWS_KEY + "\n"))

    def test_the_same_fixture_outside_tests_still_declines(self):
        self.assertTrue(self.commit_fails("src/ws.py", FIXTURE))
        self.assertTrue(self.commit_fails("src/tests.py", FIXTURE))

    def test_the_commit_message_keeps_the_full_scan(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "t.py").write_text("x = 1\n")
        result = self.analyze(self.commit_command("tests/t.py", subject='token="doesnotexist1234567890"'))
        self.assertIn("no_secret_lines", result["failed"])


if __name__ == "__main__":
    unittest.main()
