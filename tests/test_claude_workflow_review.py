"""Regression tests for findings from the security review of bin/claude-workflow.

Run from the repository root with:  python3 -B -m unittest discover -s tests

Every test uses throwaway repositories and a fake `graphify`; nothing outside
the temporary directories is touched.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BIN = Path(os.environ.get("TOOLS_BIN", Path(__file__).resolve().parents[1] / "bin"))
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.root / "a.txt").write_text("a\n")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "b.txt").write_text("b\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    def git(self, *args, cwd=None, check=True):
        r = subprocess.run(["git", *args], cwd=cwd or self.root, env=ENV, capture_output=True, text=True)
        if check:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def helper(self, *args, cwd=None, env=None):
        r = subprocess.run([sys.executable, "-B", str(BIN / "claude-workflow"), *args],
                           cwd=cwd or self.root, env=env or ENV, capture_output=True, text=True)
        try:
            data = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        except ValueError:
            data = {"unparseable": r.stdout}
        return r.returncode, data, r

    def head(self):
        return self.git("rev-parse", "HEAD")

    def commit(self, *paths, subject="s", extra=()):
        return self.helper("commit", "--expected-head", self.head(), "--subject", subject, *extra, *paths)


class RemoveNestedRepositories(Case):
    def test_nested_repository_is_never_removed(self):
        nested = self.root / "vendor" / "lib"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=nested, env=ENV, check=True)
        (nested / "work.txt").write_text("uncommitted work\n")
        for flags in (["--recursive"], ["--recursive", "--confirm"]):
            code, data, r = self.helper("remove", *flags, "vendor/lib")
            self.assertNotEqual(code, 0, flags)
            self.assertEqual(data.get("status"), "failed")
        self.assertTrue((nested / "work.txt").exists())
        self.assertTrue((nested / ".git").exists())

    def test_linked_worktree_is_never_removed(self):
        self.git("worktree", "add", "-q", "-b", "side", "wt")
        (self.root / "wt" / "dirty.txt").write_text("uncommitted\n")
        code, data, r = self.helper("remove", "--recursive", "--confirm", "wt")
        self.assertNotEqual(code, 0)
        self.assertTrue((self.root / "wt" / "dirty.txt").exists())

    def test_ordinary_directories_still_work(self):
        d = self.root / "scratch"
        d.mkdir()
        (d / "x.txt").write_text("x\n")
        code, data, r = self.helper("remove", "--recursive", "--confirm", "scratch")
        self.assertEqual(code, 0, r.stdout + r.stderr)
        self.assertFalse(d.exists())


class ProjectRootIsTheWorkingDirectory(Case):
    def test_core_worktree_cannot_redirect_removal(self):
        victim = self.base / "victim"
        victim.mkdir()
        (victim / "precious.txt").write_text("precious\n")
        (self.root / "precious.txt").write_text("mine\n")
        self.git("config", "core.worktree", str(victim))
        code, data, r = self.helper("remove", "--confirm", "precious.txt")
        self.assertNotEqual(code, 0, r.stdout)
        self.assertTrue((victim / "precious.txt").exists())
        self.assertEqual(data.get("status"), "failed")


class CommitPathspecs(Case):
    def test_magic_pathspecs_are_refused_and_staging_is_kept(self):
        (self.root / "a.txt").write_text("a2\n")
        self.git("add", "a.txt")
        (self.root / "sub" / "b.txt").write_text("b2\n")
        for spec in (":/", ":(top)sub/b.txt", ":(exclude)a.txt", ":(glob)sub/*"):
            with self.subTest(spec=spec):
                code, data, r = self.commit(spec, extra=("--leave-other-staged",))
                self.assertNotEqual(code, 0)
                self.assertEqual(self.git("diff", "--cached", "--name-only"), "a.txt")

    def test_unrelated_whitespace_error_does_not_block_a_commit(self):
        (self.root / "a.txt").write_text("trailing   \n")
        (self.root / "sub" / "b.txt").write_text("b changed\n")
        code, data, r = self.commit("sub/b.txt", subject="b only")
        self.assertEqual(code, 0, r.stdout + r.stderr)
        self.assertEqual(data.get("status"), "committed")


class MessageRules(Case):
    def test_ai_attribution_is_refused(self):
        (self.root / "a.txt").write_text("a2\n")
        cases = (
            ("--trailer", "Co-Authored-By: Claude <noreply@anthropic.com>"),
            ("--body", "Generated with [Claude Code](https://claude.com/claude-code)"),
            ("--body", "session: https://claude.ai/code/session_01abc"),
            ("--trailer", "Signed-off-by: x <noreply@anthropic.com>"),
        )
        for flag, value in cases:
            with self.subTest(value=value):
                code, data, r = self.commit("a.txt", extra=(flag, value))
                self.assertNotEqual(code, 0)
                self.assertEqual(self.git("log", "--oneline").count("\n"), 0)

    def test_messages_that_merely_mention_claude_configuration_are_allowed(self):
        (self.root / "a.txt").write_text("a2\n")
        code, data, r = self.commit("a.txt", subject="Update claude_global_config settings",
                                    extra=("--body", "Adjust the Claude Code settings policy."))
        self.assertEqual(code, 0, r.stdout + r.stderr)


class AmendPushedCommits(Case):
    def test_amending_a_commit_already_on_a_remote_is_refused(self):
        remote = self.base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], env=ENV, check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "origin", "main")
        code, data, r = self.helper("amend-message", "--expected-head", self.head(), "--subject", "rewritten")
        self.assertNotEqual(code, 0, r.stdout)
        self.assertIn("pushed", json.dumps(data).lower())
        self.assertEqual(self.git("log", "-1", "--format=%s"), "base")

    def test_explicit_override_allows_it(self):
        remote = self.base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], env=ENV, check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "origin", "main")
        code, data, r = self.helper("amend-message", "--expected-head", self.head(),
                                    "--subject", "rewritten", "--allow-pushed")
        self.assertEqual(code, 0, r.stdout + r.stderr)

    def test_unpushed_commit_amends_normally(self):
        code, data, r = self.helper("amend-message", "--expected-head", self.head(), "--subject", "fixed")
        self.assertEqual(code, 0, r.stdout + r.stderr)


class GraphOutputMustBeARealDirectory(Case):
    def test_symlinked_graph_output_is_refused(self):
        outside = self.base / "other-project-graph"
        outside.mkdir()
        marker = outside / ".claude_refresh.json"
        marker.write_text(json.dumps({"status": "prepared"}))
        (self.root / "graphify-out").symlink_to(outside)
        for command in (("graph-abort", "--confirm"), ("graph-prepare",), ("graph-finalize",)):
            with self.subTest(command=command):
                code, data, r = self.helper(*command)
                self.assertNotEqual(code, 0, r.stdout)
                self.assertIn("symlink", json.dumps(data).lower())
        self.assertTrue(marker.exists())
        self.assertEqual(sorted(p.name for p in outside.iterdir()), [".claude_refresh.json"])


class ExecutablesAndOutput(Case):
    def test_repo_supplied_graphify_is_not_executed(self):
        marker = self.base / "graphify-ran"
        planted = self.root / "bin"
        planted.mkdir()
        (planted / "graphify").write_text('#!/bin/sh\necho ran > "%s"\necho planted\n' % marker)
        (planted / "graphify").chmod(0o755)
        out = self.root / "graphify-out"
        out.mkdir()
        (out / "graph.json").write_text("{}")
        good = self.base / "goodbin"
        good.mkdir()
        (good / "graphify").write_text("#!/bin/sh\necho trusted\n")
        (good / "graphify").chmod(0o755)
        env = dict(ENV, PATH="bin:%s:%s" % (good, ENV["PATH"]))
        code, data, r = self.helper("graph-query", "question", env=env)
        self.assertFalse(marker.exists(), "a repository executable ran")
        self.assertIn("trusted", r.stdout)

    def test_origin_credentials_are_not_echoed(self):
        self.git("remote", "add", "origin", "https://user:s3cret-token@example.com/x/y.git")
        code, data, r = self.helper("project-id")
        self.assertEqual(code, 0, r.stderr)
        self.assertNotIn("s3cret-token", r.stdout)
        self.assertNotIn("user:", r.stdout)

    def test_unexpected_exceptions_are_reported_not_tracebacks(self):
        out = self.root / "graphify-out"
        out.mkdir()
        (out / ".graphify_chunk_0.json").write_bytes(b"\xff\xfe\x00bad")
        code, data, r = self.helper("graph-validate-chunk", "graphify-out/.graphify_chunk_0.json")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(data.get("status"), "failed")


class SecondReview(Case):
    """Fixes from the second independent review of bin/claude-workflow."""

    def load_module(self):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("cw_second_review", str(BIN / "claude-workflow"))
        spec = importlib.util.spec_from_loader("cw_second_review", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def test_graph_ignore_filter_does_not_run_repository_executables(self):
        marker = self.base / "python-ran"
        planted = self.root / "bin"
        planted.mkdir()
        for name in ("graphify", "python"):
            (planted / name).write_text('#!/bin/sh\necho %s >> "%s"\nexit 1\n' % (name, marker))
            (planted / name).chmod(0o755)
        module = self.load_module()
        previous = Path.cwd()
        saved = os.environ.get("PATH", "")
        os.chdir(self.root)
        os.environ["PATH"] = "bin:" + saved
        try:
            module.graph_ignored_paths(self.root, {"dirty.md"})
        finally:
            os.environ["PATH"] = saved
            os.chdir(previous)
        self.assertFalse(marker.exists(), "a repository executable ran: " + (
            marker.read_text() if marker.exists() else ""))

    def test_core_worktree_naming_an_ancestor_is_refused(self):
        (self.base / "notes.txt").write_text("sibling\n")
        (self.root / "notes.txt").write_text("mine\n")
        # core.worktree is relative to the git directory, so name the ancestor
        # absolutely (and once as "../..", which also reaches it).
        for spelling in (str(self.base), "../.."):
            self.git("config", "core.worktree", spelling)
            code, data, r = self.helper("remove", "--confirm", "notes.txt")
            self.assertNotEqual(code, 0, "%s: %s" % (spelling, r.stdout))
        self.git("config", "core.worktree", str(self.base))
        code, data, r = self.helper("remove", "--confirm", "notes.txt")
        self.assertNotEqual(code, 0, r.stdout)
        self.assertTrue((self.base / "notes.txt").exists())
        self.assertTrue((self.root / "notes.txt").exists())

    def test_bare_and_separate_git_directories_are_never_removed(self):
        subprocess.run(["git", "init", "-q", "--bare", str(self.root / "vendor" / "lib.git")],
                       env=ENV, check=True)
        subprocess.run(["git", "init", "-q", "--separate-git-dir", str(self.root / "gd"),
                        str(self.root / "vendor" / "w")], env=ENV, check=True)
        for target in ("vendor/lib.git", "gd"):
            with self.subTest(target=target):
                code, data, r = self.helper("remove", "--recursive", "--confirm", target)
                self.assertNotEqual(code, 0)
                self.assertTrue((self.root / target).exists())

    def test_targets_inside_a_nested_repository_are_refused(self):
        nested = self.root / "vendor" / "lib"
        (nested / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=nested, env=ENV, check=True)
        (nested / "src" / "f.txt").write_text("work\n")
        (nested / "g.txt").write_text("work\n")
        for flags, target in ((["--recursive"], "vendor/lib/src"), ([], "vendor/lib/g.txt")):
            with self.subTest(target=target):
                code, data, r = self.helper("remove", *flags, "--confirm", target)
                self.assertNotEqual(code, 0)
        self.assertTrue((nested / "src" / "f.txt").exists())
        self.assertTrue((nested / "g.txt").exists())

    def test_origin_credentials_are_stripped_in_every_form(self):
        secrets = {
            "https://user:p@ss@host.example/x.git": "ss@",
            "HTTPS://tok3n@host.example/x.git": "tok3n",
            "git+ssh://user:pw0rd@host.example/x": "pw0rd",
            "ssh+git://u:pw0rd@host.example/x": "pw0rd",
            "ftp://u:pw0rd@host.example/x": "pw0rd",
        }
        for url, leaked in secrets.items():
            with self.subTest(url=url):
                self.git("remote", "remove", "origin", check=False)
                self.git("remote", "add", "origin", url)
                code, data, r = self.helper("project-id")
                self.assertEqual(code, 0, r.stderr)
                self.assertNotIn(leaked, r.stdout)

    def test_attribution_guard_survives_spelling_tricks(self):
        (self.root / "a.txt").write_text("a2\n")
        trailers = ("Assisted-by: Claude", "Reviewed-by: Claude <c@x.example>", "Co-Authored-By : Claude",
                    "Co-Authored-By: Cl\u200baude <c@x.example>", "Co-Authored-By: Cl\u0430ude <c@x.example>",
                    "Generated-by: Anthropic")
        for value in trailers:
            with self.subTest(trailer=value):
                code, data, r = self.commit("a.txt", extra=("--trailer", value))
                self.assertNotEqual(code, 0, r.stdout)
        for body in ("see https://claude.com/claude-code", "made with Cl\u200baude Code, generated by Anthropic"):
            with self.subTest(body=body):
                code, data, r = self.commit("a.txt", extra=("--body", body))
                self.assertNotEqual(code, 0, r.stdout)
        self.assertEqual(self.git("log", "--oneline").count("\n"), 0)

    def test_amend_says_when_pushed_state_cannot_be_known(self):
        code, data, r = self.helper("amend-message", "--expected-head", self.head(), "--subject", "fixed")
        self.assertEqual(code, 0, r.stdout + r.stderr)
        self.assertIn("remote-tracking", data.get("note", ""))

    def test_graph_read_path_refuses_a_symlinked_output_directory(self):
        outside = self.base / "other-graph"
        outside.mkdir()
        (outside / "graph.json").write_text("{}")
        (self.root / "graphify-out").symlink_to(outside)
        for command in (("graph-query", "q"), ("graph-status",)):
            with self.subTest(command=command):
                code, data, r = self.helper(*command)
                self.assertNotEqual(code, 0, r.stdout)
                self.assertIn("symlink", json.dumps(data).lower())


class FinalReview(Case):
    def test_ordinary_messages_that_mention_the_assistant_are_accepted(self):
        (self.root / "a.txt").write_text("a2\n")
        code, data, r = self.commit(
            "a.txt", subject="Fix Claude Code session hook",
            extra=("--body", "Docs: https://docs.claude.com/en/docs/claude-code/hooks\nWritten by hand; "
                             "unrelated to anthropic tooling."))
        self.assertEqual(code, 0, r.stdout + r.stderr)

    def test_embedded_git_directory_is_not_taken_as_the_repository(self):
        evil = self.root / "evil"
        for sub in ("objects", "refs"):
            (evil / sub).mkdir(parents=True)
        (evil / "HEAD").write_text("ref: refs/heads/main\n")
        (evil / "config").write_text("[core]\n\tbare = false\n\tworktree = ..\n")
        (evil / "x.txt").write_text("x\n")
        proc = subprocess.run([sys.executable, str(BIN / "claude-workflow"), "commit", "--expected-head",
                               self.head(), "--subject", "s", "--", "x.txt"],
                              cwd=evil, env=ENV, text=True, capture_output=True)
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), self.head())


if __name__ == "__main__":
    unittest.main()
