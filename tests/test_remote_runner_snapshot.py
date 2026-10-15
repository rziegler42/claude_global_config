"""Tests for the remote-runner snapshot builder (Increment C).

Every test uses throwaway repositories. A snapshot is a commit that exists only
in a temporary repository; the source repository must be left byte-identical.
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

BIN = Path(os.environ.get("TOOLS_BIN", Path(__file__).resolve().parents[1] / "bin"))
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
CONTRACT = """[project]
id = "demo"
[profiles.quick]
command = "true"
"""


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RR = load("remote_runner_snapshot", BIN / "remote-runner")


def git(repo, *args, check=True, env=None):
    return subprocess.run(["git", *args], cwd=repo, env=env or GIT_ENV, check=check,
                          capture_output=True, text=True).stdout


class SnapshotCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve() / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.write(".gitignore", "build/\n*.log\n")
        self.write("tracked.txt", "one\n")
        self.write("gone.txt", "bye\n")
        self.write(".claude/remote-runner.toml", CONTRACT)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD").strip()

    def write(self, rel, text, mode=None):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if mode is not None:
            path.chmod(mode)

    def state(self):
        """Everything a snapshot must not change in the source repository."""
        index = (self.repo / ".git" / "index")
        return {
            "head": git(self.repo, "rev-parse", "HEAD"),
            "refs": git(self.repo, "for-each-ref"),
            "index": index.read_bytes() if index.exists() else None,
            "status": git(self.repo, "status", "--porcelain=v1", "-z", "--ignored"),
            "stash": git(self.repo, "stash", "list"),
            "objects": git(self.repo, "count-objects", "-v"),
        }

    def files_in(self, snap):
        out = git(self.repo, "--git-dir", str(snap.git_dir), "ls-tree", "-r", "--name-only",
                  snap.commit)
        return set(out.split("\n")) - {""}

    def show(self, snap, rel):
        return subprocess.run(["git", "--git-dir", str(snap.git_dir), "show", f"{snap.commit}:{rel}"],
                              env=GIT_ENV, check=True, capture_output=True).stdout

    def refused(self, fragment, **kwargs):
        with self.assertRaises(SystemExit) as caught:
            with RR.snapshot(self.repo, **kwargs):
                pass
        self.assertIn(fragment, str(caught.exception))
        return str(caught.exception)


class Contents(SnapshotCase):
    def test_modified_new_and_deleted_files(self):
        self.write("tracked.txt", "two\n")
        self.write("src/new.txt", "fresh\n")
        (self.repo / "gone.txt").unlink()
        with RR.snapshot(self.repo) as snap:
            self.assertEqual(self.show(snap, "tracked.txt"), b"two\n")
            self.assertEqual(self.show(snap, "src/new.txt"), b"fresh\n")
            self.assertNotIn("gone.txt", self.files_in(snap))
            self.assertEqual(snap.base, self.base)
            self.assertEqual(
                git(self.repo, "--git-dir", str(snap.git_dir), "rev-parse", snap.commit + "^").strip(),
                self.base)
            self.assertEqual(snap.changed, {"tracked.txt": "modified", "src/new.txt": "added",
                                            "gone.txt": "deleted"})

    def test_ignored_files_are_excluded(self):
        self.write("build/out.o", "x")
        self.write("run.log", "x")
        self.write("keep.txt", "k")
        with RR.snapshot(self.repo) as snap:
            files = self.files_in(snap)
        self.assertNotIn("build/out.o", files)
        self.assertNotIn("run.log", files)
        self.assertIn("keep.txt", files)

    def test_staged_changes_use_the_working_tree_content(self):
        self.write("tracked.txt", "staged\n")
        git(self.repo, "add", "tracked.txt")
        self.write("tracked.txt", "worktree\n")
        with RR.snapshot(self.repo) as snap:
            self.assertEqual(self.show(snap, "tracked.txt"), b"worktree\n")

    def test_staged_new_file_is_included(self):
        self.write("staged.txt", "s\n")
        git(self.repo, "add", "staged.txt")
        with RR.snapshot(self.repo) as snap:
            self.assertEqual(snap.changed.get("staged.txt"), "added")

    def test_executable_bit_and_symlink_are_preserved(self):
        self.write("run.sh", "#!/bin/sh\n", mode=0o755)
        os.symlink("tracked.txt", self.repo / "link")
        with RR.snapshot(self.repo) as snap:
            tree = git(self.repo, "--git-dir", str(snap.git_dir), "ls-tree", "-r", snap.commit)
        self.assertIn("100755", [l for l in tree.splitlines() if l.endswith("\trun.sh")][0])
        self.assertIn("120000", [l for l in tree.splitlines() if l.endswith("\tlink")][0])

    def test_clean_tree_snapshots_the_head_tree(self):
        with RR.snapshot(self.repo) as snap:
            self.assertEqual(snap.changed, {})
            tree = git(self.repo, "--git-dir", str(snap.git_dir), "rev-parse", snap.commit + "^{tree}")
        self.assertEqual(tree.strip(), git(self.repo, "rev-parse", "HEAD^{tree}").strip())

    def test_contract_is_read_from_the_snapshot(self):
        self.write(".claude/remote-runner.toml", CONTRACT.replace('"true"', '"make snap"'))
        with RR.snapshot(self.repo) as snap:
            project, profiles, _ = RR.project_config(self.repo, revision=snap.commit,
                                                     git_dir=snap.git_dir)
        self.assertEqual((project, profiles["quick"]), ("demo", "make snap"))

    def test_identity_is_fixed_and_not_the_owners(self):
        env = {**GIT_ENV, "GIT_AUTHOR_NAME": "Owner Person", "GIT_COMMITTER_NAME": "Owner Person",
               "GIT_AUTHOR_EMAIL": "owner@private.example", "GIT_COMMITTER_EMAIL": "owner@private.example"}
        self.write("tracked.txt", "two\n")
        old = os.environ.copy()
        os.environ.update(env)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(old)))
        with RR.snapshot(self.repo) as snap:
            log = git(self.repo, "--git-dir", str(snap.git_dir), "log", "-1", "--format=%an|%ae|%cn|%ce|%G?",
                      snap.commit)
        self.assertEqual(log.strip(), "remote-runner|noreply|remote-runner|noreply|N")


class SourceIsUntouched(SnapshotCase):
    def test_repository_is_unchanged(self):
        self.write("tracked.txt", "two\n")
        self.write("new.txt", "n\n")
        git(self.repo, "add", "new.txt")
        self.write("build/o", "x")
        (self.repo / "gone.txt").unlink()
        git(self.repo, "stash", "push", "-q", "-m", "keep")
        self.write("tracked.txt", "three\n")
        before = self.state()
        with RR.snapshot(self.repo):
            pass
        self.assertEqual(self.state(), before)
        self.assertEqual((self.repo / "tracked.txt").read_text(), "three\n")

    def test_temporary_repository_is_removed(self):
        with RR.snapshot(self.repo) as snap:
            where = Path(snap.git_dir)
            self.assertTrue(where.exists())
        self.assertFalse(where.exists())

    def test_hooks_and_filters_do_not_run(self):
        marker = Path(self.tmp.name) / "ran"
        hooks = self.repo / ".git" / "hooks"
        for name in ("pre-commit", "post-commit", "reference-transaction", "post-index-change"):
            hook = hooks / name
            hook.write_text("#!/bin/sh\ntouch %s\n" % marker)
            hook.chmod(0o755)
        git(self.repo, "config", "core.fsmonitor", "touch %s; false" % marker)
        git(self.repo, "config", "filter.x.clean", "touch %s; cat" % marker)
        git(self.repo, "config", "filter.x.required", "true")
        self.write(".gitattributes", "*.txt filter=x\n")
        self.write("tracked.txt", "two\n")
        self.write("new.txt", "n\n")
        with RR.snapshot(self.repo) as snap:
            self.assertEqual(self.show(snap, "new.txt"), b"n\n")
        self.assertFalse(marker.exists())


class Refusals(SnapshotCase):
    def test_unborn_head_is_refused(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        git(empty, "init", "-q", "-b", "main")
        (empty / "f").write_text("x")
        with self.assertRaises(SystemExit) as caught:
            with RR.snapshot(empty):
                pass
        self.assertIn("no commit", str(caught.exception))

    def test_private_key_file_name_is_refused_with_its_path_only(self):
        secret = "UNIQUE-SECRET-BODY-123"
        self.write("deploy/id_ed25519", secret)
        message = self.refused("deploy/id_ed25519")
        self.assertNotIn(secret, message)

    def test_credential_file_names_are_refused(self):
        for rel in (".env", "app/.env.production", "tls/server.key", ".netrc",
                    ".aws/credentials", ".git-credentials", ".pypirc", "store.p12"):
            with self.subTest(rel=rel):
                self.write(rel, "x")
                try:
                    self.refused(rel)
                finally:
                    (self.repo / rel).unlink()

    def test_env_example_is_allowed(self):
        self.write(".env.example", "KEY=\n")
        with RR.snapshot(self.repo) as snap:
            self.assertIn(".env.example", self.files_in(snap))

    def test_private_key_content_is_refused_under_any_name(self):
        body = "-----BEGIN OPENSSH PRIVATE KEY-----\nSECRETBYTES\n-----END OPENSSH PRIVATE KEY-----\n"
        self.write("notes/innocent.txt", body)
        message = self.refused("notes/innocent.txt")
        self.assertNotIn("SECRETBYTES", message)

    def test_staged_secret_is_refused(self):
        self.write(".env", "TOKEN=1\n")
        git(self.repo, "add", "-f", ".env")
        self.refused(".env")

    def test_already_committed_secret_name_is_not_rescanned(self):
        # What is in HEAD is already on origin; only what the snapshot adds is scanned.
        self.write("old/.env", "A=1\n")
        git(self.repo, "add", "-f", "old/.env")
        git(self.repo, "commit", "-q", "-m", "oops")
        with RR.snapshot(self.repo) as snap:
            self.assertEqual(snap.changed, {})

    def test_size_cap_names_the_file(self):
        self.write("big.bin", "x" * 2048)
        message = self.refused("big.bin", max_bytes=1024)
        self.assertIn("1024", message)

    def test_file_count_cap(self):
        for index in range(5):
            self.write(f"f{index}.txt", "x")
        self.refused("5 changed files", max_files=3)

    def test_symlinked_parent_directory_is_refused(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (outside / "b.txt").write_text("OUTSIDE")
        self.write("a/b.txt", "inside")
        git(self.repo, "add", "a/b.txt")
        git(self.repo, "commit", "-q", "-m", "a")
        (self.repo / "a" / "b.txt").unlink()
        (self.repo / "a").rmdir()
        os.symlink(outside, self.repo / "a")
        with self.assertRaises(SystemExit) as caught:
            with RR.snapshot(self.repo) as snap:
                self.assertNotIn(b"OUTSIDE", self.show(snap, "a/b.txt"))
        self.assertIn("a/b.txt", str(caught.exception))

    def test_fifo_is_not_read_or_included(self):
        os.mkfifo(self.repo / "pipe")
        with RR.snapshot(self.repo) as snap:
            self.assertNotIn("pipe", self.files_in(snap))

    def test_tracked_fifo_replacement_is_refused_not_read(self):
        (self.repo / "tracked.txt").unlink()
        os.mkfifo(self.repo / "tracked.txt")
        self.refused("tracked.txt")

    def test_pem_is_refused_only_with_a_private_key(self):
        self.write("ca.pem", "-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----\n")
        with RR.snapshot(self.repo) as snap:
            self.assertIn("ca.pem", self.files_in(snap))
        self.write("srv.pem", "-----BEGIN RSA PRIVATE KEY-----\nBBB\n")
        self.refused("srv.pem")

    def test_large_unchanged_tracked_file_is_not_refused(self):
        self.write("blob.bin", "y" * 4096)
        git(self.repo, "add", "blob.bin")
        git(self.repo, "commit", "-q", "-m", "blob")
        with RR.snapshot(self.repo, max_bytes=1024) as snap:
            self.assertEqual(snap.changed, {})

    def test_filemode_false_keeps_index_modes(self):
        self.write("run.sh", "#!/bin/sh\n", mode=0o755)
        git(self.repo, "add", "run.sh")
        git(self.repo, "commit", "-q", "-m", "x")
        git(self.repo, "config", "core.fileMode", "false")
        (self.repo / "run.sh").chmod(0o644)
        with RR.snapshot(self.repo) as snap:
            self.assertEqual(snap.changed, {})

    def test_nested_repository_is_not_followed(self):
        nested = self.repo / "vendor" / "lib"
        nested.mkdir(parents=True)
        git(nested, "init", "-q")
        (nested / "code.py").write_text("print()\n")
        with RR.snapshot(self.repo) as snap:
            self.assertFalse([f for f in self.files_in(snap) if f.startswith("vendor/")])


if __name__ == "__main__":
    unittest.main()
