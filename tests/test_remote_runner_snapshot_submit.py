"""Tests for snapshot submission: bundle transport and the submit-snapshot worker action.

A fake `ssh` runs the "remote" command on this machine, so the real controller
and real worker exchange a real bundle. Nothing is sent to a real host.
"""
import base64
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True

BIN = Path(os.environ.get("TOOLS_BIN", Path(__file__).resolve().parents[1] / "bin"))
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull}
CONTRACT = """[project]
id = "snapdemo"
[profiles.quick]
command = "test \\"$(cat new.txt)\\" = fresh && grep -q two tracked.txt"
"""


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RR = load("remote_runner_snapshot_submit", BIN / "remote-runner")


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode()


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV}, check=True,
                          capture_output=True, text=True).stdout


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base_dir = Path(self.tmp.name).resolve()
        self.origin = self.base_dir / "origin.git"
        self.ws = self.base_dir / "ws"
        self.repo = self.base_dir / "work"
        fake = self.base_dir / "bin" / "ssh"
        fake.parent.mkdir()
        fake.write_text('#!/bin/sh\nwhile [ "$#" -gt 0 ]; do case "$1" in -o) shift 2;; -*) shift;; *) break;; '
                        'esac; done\nshift\nexec sh -c "$*"\n')
        fake.chmod(0o755)
        patcher = mock.patch.dict(os.environ, {**GIT_ENV, "GIT_SSH": str(fake),
                                               "PATH": f"{fake.parent}:{os.environ['PATH']}"})
        patcher.start()
        self.addCleanup(patcher.stop)
        git(self.base_dir, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(self.base_dir, "init", "-q", "-b", "main", str(self.repo))
        self.url = "ssh://git@fakehost%s" % self.origin
        git(self.repo, "remote", "add", "origin", self.url)
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "remote-runner.toml").write_text(CONTRACT)
        (self.repo / "tracked.txt").write_text("one\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "push", "-q", "origin", "main")
        self.head = git(self.repo, "rev-parse", "HEAD").strip()
        (self.repo / "tracked.txt").write_text("two\n")
        (self.repo / "new.txt").write_text("fresh\n")
        remotes = {"r1": {"ssh_host": "fakehost", "workspace_root": str(self.ws), "max_jobs": 2}}
        patcher = mock.patch.object(RR, "load_remotes", lambda: remotes)
        patcher.start()
        self.addCleanup(patcher.stop)
        previous = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)

    def controller(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            RR.controller(RR.parser().parse_args(list(argv)))
        return out.getvalue()

    def wait(self, job):
        deadline = time.time() + 20
        while time.time() < deadline:
            status = json.loads(self.controller("status", job))
            if status["state"] not in ("RUNNING", "STARTING"):
                return status
            time.sleep(0.2)
        self.fail("job did not finish")

    def worker(self, *arguments, stdin=b""):
        args = RR.worker_parser().parse_args(
            ["--worker", *arguments, "--workspace-root", str(self.ws), "--max-jobs", "2"])
        out = io.StringIO()
        fake_stdin = mock.Mock(buffer=io.BytesIO(stdin))
        with mock.patch.object(sys, "stdin", fake_stdin), contextlib.redirect_stdout(out):
            RR.worker(args)
        return out.getvalue()

    def bundle(self):
        with RR.snapshot(self.repo) as snap:
            path = self.base_dir / "payload.bundle"
            size, digest = RR.make_bundle(snap, path)
            return snap.commit, snap.base, path.read_bytes(), size, digest

    def submit_args(self, job, commit, base, size, digest, **overrides):
        values = {"--job": job, "--project": b64("snapdemo"), "--source-url": b64(self.url),
                  "--source-ref": b64("refs/heads/main"), "--commit": commit, "--base": base,
                  "--bundle-size": str(size), "--bundle-sha256": digest,
                  "--command": b64("true"), **overrides}
        return ["submit-snapshot", *[x for pair in values.items() for x in pair]]


class EndToEnd(Fixture):
    def test_snapshot_job_runs_uncommitted_work_with_provenance(self):
        before = {"head": git(self.repo, "rev-parse", "HEAD"),
                  "status": git(self.repo, "status", "--porcelain"),
                  "refs": git(self.repo, "for-each-ref"),
                  "index": (self.repo / ".git" / "index").read_bytes()}
        data = json.loads(self.controller("submit", "--snapshot", "--remote", "r1",
                                          "--profile", "quick"))
        self.assertIs(data["snapshot"], True)
        self.assertEqual(data["base_commit"], self.head)
        self.assertNotEqual(data["commit"], self.head)
        self.assertEqual(data["dut_commit"], data["commit"])
        self.assertIs(data["dut_clean"], True)
        status = self.wait(data["job"])
        self.assertEqual(status["state"], "PASSED")
        self.assertEqual(status["integrity"], "ok")
        self.assertIs(status["snapshot"], True)
        self.assertEqual(status["base_commit"], self.head)
        self.assertEqual(status["commit"], data["commit"])
        after = {"head": git(self.repo, "rev-parse", "HEAD"),
                 "status": git(self.repo, "status", "--porcelain"),
                 "refs": git(self.repo, "for-each-ref"),
                 "index": (self.repo / ".git" / "index").read_bytes()}
        self.assertEqual(after, before)

    def test_snapshot_flag_conflicts_with_ref(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            RR.parser().parse_args(["submit", "--snapshot", "--ref", "main", "--remote", "r1",
                                    "--profile", "quick"])

    def test_default_submit_is_unchanged(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "work")
        git(self.repo, "push", "-q", "origin", "main")
        data = json.loads(self.controller("submit", "--remote", "r1", "--profile", "quick"))
        self.assertNotIn("snapshot", data)
        self.assertEqual(self.wait(data["job"])["state"], "PASSED")

    def test_unpushed_base_is_reported_and_leaves_nothing(self):
        (self.repo / "later.txt").write_text("x")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "unpushed")
        with self.assertRaises(SystemExit) as caught:
            self.controller("submit", "--snapshot", "--remote", "r1", "--profile", "quick")
        self.assertIn("push", str(caught.exception))
        self.assertEqual(list((self.ws / "jobs").glob("*--*")), [])

    def test_prune_removes_snapshot_ref_bundle_and_worktree(self):
        data = json.loads(self.controller("submit", "--snapshot", "--remote", "r1",
                                          "--profile", "quick"))
        self.wait(data["job"])
        job_dir = self.ws / "jobs" / data["job"]
        self.assertFalse((job_dir / "snapshot.bundle").exists())
        bare = next((self.ws / "projects").glob("*/repo.git"))
        ref = f"refs/snapshots/{data['job']}"
        self.assertIn(ref, git(bare, "for-each-ref", "--format=%(refname)"))
        self.controller("prune", "--remote", "r1", "--success-days", "0", "--apply")
        self.assertFalse(job_dir.exists())
        self.assertNotIn(ref, git(bare, "for-each-ref", "--format=%(refname)"))
        self.assertNotIn(str(job_dir), git(bare, "worktree", "list"))


class ReviewFindings(Fixture):
    def finished_job(self):
        data = json.loads(self.controller("submit", "--snapshot", "--remote", "r1",
                                          "--profile", "quick"))
        self.wait(data["job"])
        return data["job"]

    def test_bundle_is_deleted_after_the_verified_fetch(self):
        job = self.finished_job()
        self.assertFalse((self.ws / "jobs" / job / "snapshot.bundle").exists())

    def test_prune_removes_the_ref_even_when_the_record_names_another_cache(self):
        job = self.finished_job()
        bare = next((self.ws / "projects").glob("*/repo.git"))
        record = self.ws / "jobs" / job / "metadata.json"
        data = json.loads(record.read_text())
        data["cache"] = "somewhere-else"
        record.write_text(json.dumps(data))
        self.controller("prune", "--remote", "r1", "--success-days", "0", "--apply")
        self.assertNotIn(f"refs/snapshots/{job}", git(bare, "for-each-ref", "--format=%(refname)"))

    def test_prune_removes_the_ref_of_a_job_with_a_minimal_record(self):
        job = self.finished_job()
        bare = next((self.ws / "projects").glob("*/repo.git"))
        record = self.ws / "jobs" / job / "metadata.json"
        record.write_text(json.dumps({"job": job, "project": "snapdemo", "state": "FAILED",
                                      "created_at": 1.0}))
        self.controller("prune", "--remote", "r1", "--success-days", "0", "--failure-days", "0",
                        "--apply")
        self.assertNotIn(f"refs/snapshots/{job}", git(bare, "for-each-ref", "--format=%(refname)"))

    def test_hostile_source_ref_is_refused_by_the_worker(self):
        marker = self.base_dir / "MARK"
        commit, base, data, size, digest = self.bundle()
        args = self.submit_args("src-1", commit, base, size, digest,
                                **{"--source-ref": b64(f"--upload-pack=touch {marker}")})
        with self.assertRaises(SystemExit):
            self.worker(*args, stdin=data)
        self.assertFalse(marker.exists())
        self.assertFalse((self.ws / "jobs" / "src-1").exists())

    def test_terminated_submit_leaves_no_temporary_copies(self):
        scratch = self.base_dir / "tmp"
        scratch.mkdir()
        code = (
            "import importlib.machinery as m, importlib.util as u, sys, time, os\n"
            "l=m.SourceFileLoader('rr', sys.argv[1]); s=u.spec_from_loader('rr', l)\n"
            "rr=u.module_from_spec(s); l.exec_module(rr)\n"
            "rr.load_remotes=lambda: {'r1': {'ssh_host':'h','workspace_root':'/x','max_jobs':1}}\n"
            "def slow(*a, **k):\n"
            "    print('READY', flush=True); time.sleep(60)\n"
            "rr.invoke_worker=slow\n"
            "args=rr.parser().parse_args(['submit','--snapshot','--remote','r1','--profile','quick'])\n"
            "rr.controller(args)\n")
        env = {**os.environ, "TMPDIR": str(scratch)}
        process = subprocess.Popen([sys.executable, "-I", "-c", code, str(BIN / "remote-runner")],
                                   cwd=self.repo, env=env, stdout=subprocess.PIPE, text=True)
        self.assertEqual(process.stdout.readline().strip(), "READY")
        self.assertTrue(list(scratch.glob("remote-runner-*")))
        process.terminate()
        process.wait(timeout=20)
        self.assertEqual(list(scratch.glob("remote-runner-*")), [])


class Bootstrap(unittest.TestCase):
    def test_bootstrap_leaves_the_rest_of_stdin_to_the_script(self):
        script = b"import sys\nprint(len(sys.stdin.buffer.read()), sys.argv[1:])\n"
        payload = b"%d\n" % len(script) + script + b"B" * 5000
        result = subprocess.run([sys.executable, "-I", "-c", RR.BOOTSTRAP, "--x", "y"],
                                input=payload, capture_output=True, check=True)
        self.assertEqual(result.stdout.decode().strip(), "5000 ['--x', 'y']")

    def test_bootstrap_rejects_a_hostile_length(self):
        for header in (b"-1\n", b"abc\n", b"99999999999\n"):
            result = subprocess.run([sys.executable, "-I", "-c", RR.BOOTSTRAP], input=header + b"x",
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0, header)


class WorkerBundle(Fixture):
    def attempt(self, job, mutate=None, **overrides):
        commit, base, data, size, digest = self.bundle()
        if mutate is not None:
            data, size, digest = mutate(data, size, digest)
        args = self.submit_args(job, commit, base, size, digest, **overrides)
        return commit, self.worker(*args, stdin=data)

    def assert_clean_refusal(self, job, fragment, mutate=None, **overrides):
        with self.assertRaises(SystemExit) as caught:
            self.attempt(job, mutate, **overrides)
        self.assertIn(fragment, str(caught.exception))
        self.assertFalse((self.ws / "jobs" / job).exists())
        for bare in (self.ws / "projects").glob("*/repo.git"):
            self.assertNotIn(job, git(bare, "for-each-ref", "--format=%(refname)"))

    def test_good_bundle_is_accepted(self):
        commit, output = self.attempt("good-1")
        data = json.loads(output)
        self.assertEqual(data["dut_commit"], commit)
        self.assertIs(data["dut_clean"], True)

    def test_corrupt_bundle_is_rejected(self):
        def corrupt(data, size, digest):
            damaged = data[:-20] + b"\0" * 20
            return damaged, len(damaged), hashlib.sha256(damaged).hexdigest()
        self.assert_clean_refusal("bad-1", "bundle", corrupt)

    def test_digest_mismatch_is_rejected(self):
        self.assert_clean_refusal("bad-2", "digest",
                                  lambda d, s, h: (d, s, "0" * 64))

    def test_truncated_stream_is_rejected(self):
        self.assert_clean_refusal("bad-3", "bundle",
                                  lambda d, s, h: (d[:-1], s, h))

    def test_trailing_bytes_are_rejected(self):
        self.assert_clean_refusal("bad-4", "trailing",
                                  lambda d, s, h: (d + b"extra", s, h))

    def test_oversized_declaration_is_rejected_before_reading(self):
        with mock.patch.object(RR, "BUNDLE_LIMIT", 10):
            self.assert_clean_refusal("bad-5", "limit")

    def test_commit_mismatch_is_rejected(self):
        self.assert_clean_refusal("bad-6", "does not match", **{"--commit": "1" * 40})

    def test_wrong_base_is_rejected(self):
        self.assert_clean_refusal("bad-7", "base", **{"--base": "2" * 40})

    def test_invalid_arguments_are_rejected(self):
        for name, value in (("--commit", "xyz"), ("--base", "not-a-sha"),
                            ("--bundle-sha256", "short"), ("--bundle-size", "-4")):
            with self.subTest(name=name):
                commit, base, data, size, digest = self.bundle()
                args = self.submit_args("bad-8", commit, base, size, digest, **{name: value})
                with self.assertRaises(SystemExit):
                    self.worker(*args, stdin=data)
                self.assertFalse((self.ws / "jobs" / "bad-8").exists())


if __name__ == "__main__":
    unittest.main()
