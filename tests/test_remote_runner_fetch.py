"""Tests for `remote-runner fetch`: argument validation, safe local placement, and the
worker/controller transport.

A fake `ssh` runs the "remote" command on this machine, so the real controller and
real worker exchange real bytes. Nothing is sent to a real host.
"""
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
from unittest import mock

sys.dont_write_bytecode = True

BIN = Path(os.environ.get("TOOLS_BIN", Path(__file__).resolve().parents[1] / "bin"))
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull}
JOB = "r1--proj--20261016-120000--abcd1234"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RR = load("remote_runner_fetch", BIN / "remote-runner")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV}, check=True,
                          capture_output=True, text=True).stdout


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name).resolve()
        self.repo = self.dir / "repo"
        git(self.dir, "init", "-q", "-b", "main", str(self.repo))
        (self.repo / "tracked.txt").write_text("tracked\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        previous = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)

    def files(self, root):
        return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*")
                      if not p.is_dir() and ".git" not in p.relative_to(root).parts)


class PathValidation(unittest.TestCase):
    def test_accepts_ordinary_relative_paths(self):
        for path in ("a", "checkpoints/latest.pt", "a/b/c.bin", "with space/x y.pt"):
            self.assertEqual(RR.validate_fetch_path(path), path.split("/"))

    def test_refuses_unsafe_paths(self):
        for path in ("", "/etc/passwd", "../x", "a/../b", "a//b", "a/./b", "./a", "a/", "-x",
                     "a/\0b", "a\nb", "x" * 2000, "a/..", "\x7f"):
            with self.assertRaises(SystemExit, msg=repr(path)):
                RR.validate_fetch_path(path)

    def test_refuses_unsafe_replacement_names(self):
        for name in ("", ".", "..", "a/b", "-x", "a\0b", "a\nb", "x" * 300):
            with self.assertRaises(SystemExit, msg=repr(name)):
                RR.validate_fetch_name(name)
        self.assertEqual(RR.validate_fetch_name("model-v3.pt"), "model-v3.pt")


class ArgumentRules(Base):
    def parse(self, *argv):
        return RR.parser().parse_args(["fetch", *argv])

    def controller(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            RR.controller(self.parse(*argv))
        return out.getvalue()

    def test_as_needs_exactly_one_path(self):
        with mock.patch.object(RR, "fetch_session") as invoke:
            with self.assertRaises(SystemExit) as caught:
                self.controller(JOB, "a.pt", "b.pt", "--as", "x.pt")
            self.assertIn("--as", str(caught.exception))
            invoke.assert_not_called()

    def test_bad_names_and_paths_are_refused_before_any_ssh_call(self):
        cases = [(JOB, "../x"), (JOB, "/abs"), (JOB, "-x"), (JOB, "a", "--as", "b/c"),
                 (JOB, "a", "--as", ".."), (JOB, "a", "--as", "-x"), (JOB, "a", "--as", "")]
        for argv in cases:
            with mock.patch.object(RR, "fetch_session") as invoke:
                with self.assertRaises(SystemExit, msg=argv):
                    self.controller(*argv)
                invoke.assert_not_called()

    def test_paths_that_collide_on_a_case_insensitive_disk_are_refused(self):
        with mock.patch.object(RR, "fetch_session") as invoke:
            with self.assertRaises(SystemExit):
                self.controller(JOB, "A.pt", "a.pt")
            invoke.assert_not_called()

    def test_too_many_and_duplicate_paths_are_refused(self):
        with mock.patch.object(RR, "fetch_session") as invoke:
            with self.assertRaises(SystemExit):
                self.controller(JOB, *[f"f{i}" for i in range(17)])
            with self.assertRaises(SystemExit):
                self.controller(JOB, "a", "a")
            invoke.assert_not_called()

    def test_missing_dest_is_refused(self):
        with mock.patch.object(RR, "fetch_session") as invoke:
            with self.assertRaises(SystemExit):
                self.controller(JOB, "a", "--dest", str(self.dir / "nope"))
            invoke.assert_not_called()

    def test_dest_must_be_a_directory(self):
        (self.dir / "file").write_text("x")
        with self.assertRaises(SystemExit):
            self.controller(JOB, "a", "--dest", str(self.dir / "file"))


class Placement(Base):
    def target(self, parts, **kwargs):
        base = kwargs.pop("base", self.repo)
        return RR.check_fetch_target(base, parts, repo=self.repo, force=kwargs.pop("force", False))

    def test_default_dest_and_rename_placement(self):
        base = self.repo
        self.assertEqual(RR.fetch_target_parts(["checkpoints", "latest.pt"], None),
                         ["checkpoints", "latest.pt"])
        self.assertEqual(RR.fetch_target_parts(["checkpoints", "latest.pt"], "model-v3.pt"),
                         ["checkpoints", "model-v3.pt"])
        self.assertEqual(RR.fetch_target_parts(["latest.pt"], "m.pt"), ["m.pt"])
        self.assertEqual(self.target(["checkpoints", "latest.pt"]),
                         base / "checkpoints" / "latest.pt")

    def test_existing_target_needs_force(self):
        (self.repo / "w.pt").write_text("old")
        with self.assertRaises(SystemExit) as caught:
            self.target(["w.pt"])
        self.assertIn("--force", str(caught.exception))
        self.target(["w.pt"], force=True)

    def test_tracked_target_needs_force_even_when_missing_on_disk(self):
        (self.repo / "tracked.txt").unlink()
        with self.assertRaises(SystemExit) as caught:
            self.target(["tracked.txt"])
        self.assertIn("tracked", str(caught.exception))

    def test_tracked_target_is_allowed_with_force(self):
        (self.repo / "tracked.txt").unlink()
        self.target(["tracked.txt"], force=True)

    def test_symlinked_directory_component_is_refused_even_with_force(self):
        outside = self.dir / "outside"
        outside.mkdir()
        (self.repo / "link").symlink_to(outside)
        for force in (False, True):
            with self.assertRaises(SystemExit, msg=force):
                self.target(["link", "w.pt"], force=force)

    def test_symlink_at_target_is_refused_without_following(self):
        outside = self.dir / "outside.txt"
        outside.write_text("keep")
        (self.repo / "w.pt").symlink_to(outside)
        with self.assertRaises(SystemExit):
            self.target(["w.pt"])
        self.assertEqual(outside.read_text(), "keep")

    def test_directory_at_target_is_refused(self):
        (self.repo / "w.pt").mkdir()
        with self.assertRaises(SystemExit):
            self.target(["w.pt"], force=True)

    def test_file_component_is_refused(self):
        (self.repo / "a").write_text("x")
        with self.assertRaises(SystemExit):
            self.target(["a", "w.pt"])

    def test_git_metadata_is_never_a_target_even_with_force(self):
        for parts in ([".git", "hooks", "pre-commit"], [".GIT", "config"], ["sub", ".git", "x"]):
            for force in (False, True):
                with self.assertRaises(SystemExit, msg=(parts, force)) as caught:
                    self.target(parts, force=force)
                self.assertIn(".git", str(caught.exception).lower())

    def test_claude_configuration_needs_force(self):
        for parts in ([".claude", "settings.local.json"], [".Claude", "x"]):
            with self.assertRaises(SystemExit, msg=parts) as caught:
                self.target(parts)
            self.assertIn("--force", str(caught.exception))
        self.target([".claude", "settings.local.json"], force=True)

    def test_dest_outside_repo_skips_the_tracked_check(self):
        dest = self.dir / "weights"
        dest.mkdir()
        self.assertEqual(self.target(["tracked.txt"], base=dest), dest / "tracked.txt")


HEX = "a" * 40


class Transport(Base):
    """Real controller and real worker joined by a shim `ssh` that runs the command locally."""

    def setUp(self):
        super().setUp()
        self.ws = self.dir / "ws"
        self.job_dir = self.ws / "jobs" / JOB
        (self.job_dir / "worktree" / "checkpoints").mkdir(parents=True)
        self.work = self.job_dir / "worktree"
        fake = self.dir / "bin" / "ssh"
        fake.parent.mkdir()
        fake.write_text('#!/bin/sh\nwhile [ "$#" -gt 0 ]; do case "$1" in -o) shift 2;; -*) shift;; *) break;; '
                        'esac; done\nshift\nexec sh -c "$*"\n')
        fake.chmod(0o755)
        patcher = mock.patch.dict(os.environ, {**GIT_ENV, "PATH": f"{fake.parent}:{os.environ['PATH']}"})
        patcher.start()
        self.addCleanup(patcher.stop)
        remotes = {"r1": {"ssh_host": "fakehost", "workspace_root": str(self.ws), "max_jobs": 2}}
        patcher = mock.patch.object(RR, "load_remotes", lambda: remotes)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.set_state("PASSED")
        self.weights = os.urandom(300_000)
        (self.work / "checkpoints" / "latest.pt").write_bytes(self.weights)

    def set_state(self, state, **extra):
        record = {"job": JOB, "project": "proj", "commit": HEX, "dut_commit": HEX, "dut_clean": True,
                  "state": state, "created_at": time.time(), **extra}
        (self.job_dir / "metadata.json").write_text(json.dumps(record))

    def fetch(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            RR.controller(RR.parser().parse_args(["fetch", JOB, *argv]))
        return json.loads(out.getvalue())

    def refused(self, *argv):
        with self.assertRaises(SystemExit) as caught:
            self.fetch(*argv)
        return str(caught.exception)

    def leftovers(self):
        return [p for p in self.files(self.repo) if p.startswith(".rr-fetch") or p.endswith(".tmp")]


class EndToEnd(Transport):
    def test_file_arrives_at_the_same_relative_path_with_provenance(self):
        data = self.fetch("checkpoints/latest.pt")
        target = self.repo / "checkpoints" / "latest.pt"
        self.assertEqual(target.read_bytes(), self.weights)
        entry = data["files"][0]
        self.assertEqual(entry["sha256"], hashlib.sha256(self.weights).hexdigest())
        self.assertEqual(entry["bytes"], len(self.weights))
        self.assertEqual(entry["remote_path"], "checkpoints/latest.pt")
        self.assertEqual(entry["local_path"], str(target))
        self.assertEqual((data["dut_commit"], data["integrity"], data["state"]), (HEX, "ok", "PASSED"))
        self.assertIs(data["untrusted_job_data"], True)
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.leftovers(), [])

    def test_rename_dest_and_both(self):
        self.fetch("checkpoints/latest.pt", "--as", "model-v3.pt")
        self.assertEqual((self.repo / "checkpoints" / "model-v3.pt").read_bytes(), self.weights)
        dest = self.dir / "weights"
        dest.mkdir()
        self.fetch("checkpoints/latest.pt", "--dest", str(dest))
        self.assertEqual((dest / "checkpoints" / "latest.pt").read_bytes(), self.weights)
        self.fetch("checkpoints/latest.pt", "--dest", str(dest), "--as", "m.pt")
        self.assertEqual((dest / "checkpoints" / "m.pt").read_bytes(), self.weights)

    def test_several_files_and_an_empty_file(self):
        (self.work / "empty.bin").write_bytes(b"")
        (self.work / "note.txt").write_text("hello")
        data = self.fetch("empty.bin", "note.txt", "checkpoints/latest.pt")
        self.assertEqual([f["bytes"] for f in data["files"]], [0, 5, len(self.weights)])
        self.assertEqual((self.repo / "empty.bin").read_bytes(), b"")
        self.assertEqual((self.repo / "note.txt").read_text(), "hello")

    def test_existing_target_is_kept_without_force_and_replaced_with_it(self):
        (self.repo / "checkpoints").mkdir()
        existing = self.repo / "checkpoints" / "latest.pt"
        existing.write_bytes(b"old")
        self.assertIn("--force", self.refused("checkpoints/latest.pt"))
        self.assertEqual(existing.read_bytes(), b"old")
        self.fetch("checkpoints/latest.pt", "--force")
        self.assertEqual(existing.read_bytes(), self.weights)
        self.assertEqual(self.leftovers(), [])

    def test_tracked_target_is_refused_until_forced(self):
        (self.work / "tracked.txt").write_text("remote")
        self.assertIn("tracked", self.refused("tracked.txt"))
        self.assertEqual((self.repo / "tracked.txt").read_text(), "tracked\n")

    def test_every_state_that_is_not_finished_is_refused(self):
        for state in ("RUNNING", "STARTING", "CANCELLED", "UNKNOWN_EXIT"):
            self.set_state(state)
            self.assertIn("finished", self.refused("checkpoints/latest.pt"), state)
        self.assertEqual(self.files(self.repo), ["tracked.txt"])

    def test_a_record_claiming_finished_while_the_process_lives_is_refused(self):
        sleeper = subprocess.Popen(["sleep", "30"])
        self.addCleanup(sleeper.wait)
        self.addCleanup(sleeper.kill)
        self.set_state("PASSED", pid=sleeper.pid, pid_start=RR.process_start(sleeper.pid))
        self.assertIn("finished", self.refused("checkpoints/latest.pt"))

    def test_missing_unknown_and_non_regular_files_are_refused(self):
        self.assertIn("cannot open", self.refused("checkpoints/nope.pt"))
        self.assertIn("cannot open", self.refused("nodir/x"))
        (self.work / "adir").mkdir()
        self.assertIn("not a regular file", self.refused("adir"))
        os.mkfifo(self.work / "pipe")
        self.assertIn("not a regular file", self.refused("pipe"))
        self.assertEqual(self.files(self.repo), ["tracked.txt"])

    def test_symlinks_in_the_job_tree_are_never_followed(self):
        secret = self.dir / "secret.txt"
        secret.write_text("secret")
        (self.work / "leak.txt").symlink_to(secret)
        (self.work / "linkdir").symlink_to(self.dir)
        for path in ("leak.txt", "linkdir/secret.txt"):
            self.assertIn("cannot open", self.refused(path), path)
        self.assertEqual(self.files(self.repo), ["tracked.txt"])

    def test_a_symlinked_worktree_is_not_followed(self):
        real = self.dir / "elsewhere"
        real.mkdir()
        (real / "x").write_text("x")
        self.work.rename(self.job_dir / "worktree.bak")
        (self.job_dir / "worktree").symlink_to(real)
        self.assertIn("cannot open", self.refused("x"))

    def test_too_many_bytes_are_refused(self):
        with mock.patch.object(RR, "FETCH_MAX_BYTES", 1000):
            self.assertIn("limit", self.refused("checkpoints/latest.pt"))
        self.assertEqual(self.files(self.repo), ["tracked.txt"])

    def test_unknown_job_is_reported(self):
        out = io.StringIO()
        with self.assertRaises(SystemExit) as caught:
            RR.controller(RR.parser().parse_args(["fetch", "r1--proj--20261016-120000--ffffffff", "a"]))
        self.assertIn("unknown job", str(caught.exception))


class Reporting(Transport):
    def test_a_partial_placement_names_what_was_already_placed(self):
        (self.work / "b.pt").write_bytes(b"b")
        (self.repo / "b.pt").mkdir()          # appears as a directory after the pre-check
        real = RR.check_fetch_target

        def lenient(base, parts, **kwargs):
            if parts == ["b.pt"]:
                return base / "b.pt"
            return real(base, parts, **kwargs)

        with mock.patch.object(RR, "check_fetch_target", lenient):
            message = self.refused("checkpoints/latest.pt", "b.pt")
        self.assertIn("already placed", message)
        self.assertIn("checkpoints/latest.pt", message)

    def test_worker_command_passes_paths_as_joined_options(self):
        seen = []
        real = RR.worker_ssh_command

        def spy(*args, **kwargs):
            seen.append(args)
            return real(*args, **kwargs)

        with mock.patch.object(RR, "worker_ssh_command", spy):
            self.fetch("checkpoints/latest.pt")
        self.assertTrue(all(a.startswith("--fetch-path=") for a in seen[0][4::1][:1]))


class HostileStreams(Transport):
    """A runner (or a tampered worker) that sends something other than the protocol."""

    def stream(self, payload, code=0):
        script = self.dir / "evil.py"
        script.write_bytes(b"import sys\nsys.stdout.buffer.write(%r)\nsys.stdout.buffer.flush()\n"
                           b"sys.exit(%d)\n" % (payload, code))
        return mock.patch.object(RR, "worker_ssh_command",
                                 lambda *a, **k: [sys.executable, str(script)])

    def header(self, files, job=None):
        return RR.FETCH_MAGIC + json.dumps(
            {"job": job or {"state": "PASSED", "dut_commit": HEX, "integrity": "ok"},
             "files": files}).encode() + b"\n"

    def run_bad(self, payload, code=0, expect=""):
        with self.stream(payload, code):
            message = self.refused("checkpoints/latest.pt")
        self.assertIn(expect, message)
        self.assertEqual(self.files(self.repo), ["tracked.txt"])

    def good(self, data):
        return data + hashlib.sha256(data).hexdigest().encode() + b"\n"

    def test_a_correct_hostile_stream_is_the_baseline(self):
        data = b"abc"
        payload = self.header([{"path": "checkpoints/latest.pt", "size": 3}]) + self.good(data)
        with self.stream(payload):
            self.fetch("checkpoints/latest.pt")
        self.assertEqual((self.repo / "checkpoints" / "latest.pt").read_bytes(), b"abc")

    def test_wrong_digest_leaves_nothing(self):
        payload = (self.header([{"path": "checkpoints/latest.pt", "size": 3}]) + b"abc"
                   + b"0" * 64 + b"\n")
        self.run_bad(payload, expect="checksum")

    def test_truncated_stream_leaves_nothing(self):
        payload = self.header([{"path": "checkpoints/latest.pt", "size": 10}]) + b"abc"
        self.run_bad(payload, expect="ended")

    def test_extra_data_leaves_nothing(self):
        payload = (self.header([{"path": "checkpoints/latest.pt", "size": 3}])
                   + self.good(b"abc") + b"extra")
        self.run_bad(payload, expect="extra")

    def test_a_name_that_was_not_requested_is_refused(self):
        payload = self.header([{"path": "../../evil", "size": 3}]) + self.good(b"abc")
        self.run_bad(payload, expect="does not match")

    def test_extra_or_missing_frames_are_refused(self):
        entry = {"path": "checkpoints/latest.pt", "size": 3}
        self.run_bad(self.header([entry, entry]) + self.good(b"abc") * 2, expect="does not match")
        self.run_bad(self.header([]), expect="does not match")

    def test_oversized_claims_are_refused_before_any_bytes_are_read(self):
        payload = self.header([{"path": "checkpoints/latest.pt", "size": RR.FETCH_MAX_BYTES + 1}])
        self.run_bad(payload, expect="limit")

    def test_bad_sizes_and_garbage_headers_are_refused(self):
        for size in (-1, True, "3", 1.5, None):
            self.run_bad(self.header([{"path": "checkpoints/latest.pt", "size": size}]),
                         expect="does not match")
        self.run_bad(b"hello\n", expect="fetch stream")
        self.run_bad(RR.FETCH_MAGIC + b"not json\n", expect="")
        self.run_bad(RR.FETCH_MAGIC + b"x" * (RR.FETCH_HEADER_LIMIT + 10), expect="header")

    def test_a_failing_worker_is_reported_even_after_a_complete_stream(self):
        payload = self.header([{"path": "checkpoints/latest.pt", "size": 3}]) + self.good(b"abc")
        self.run_bad(payload, code=3, expect="failure")

    def test_hostile_job_view_fields_are_not_echoed(self):
        job = {"state": "PASSED\x1b[31m", "dut_commit": "not-a-commit", "integrity": "fine",
               "commit": "z" * 40}
        payload = self.header([{"path": "checkpoints/latest.pt", "size": 3}], job=job) + self.good(b"abc")
        with self.stream(payload):
            data = self.fetch("checkpoints/latest.pt")
        self.assertEqual((data["state"], data["dut_commit"], data["integrity"], data["commit"]),
                         ("UNKNOWN", None, "invalid", None))

    def test_a_symlink_swapped_in_after_the_check_is_not_followed(self):
        outside = self.dir / "outside"
        outside.mkdir()
        payload = self.header([{"path": "checkpoints/latest.pt", "size": 3}]) + self.good(b"abc")
        real = RR.receive_fetch

        def swap(*args, **kwargs):
            (self.repo / "checkpoints").symlink_to(outside)
            return real(*args, **kwargs)

        with self.stream(payload), mock.patch.object(RR, "receive_fetch", swap):
            self.refused("checkpoints/latest.pt")
        self.assertEqual(list(outside.iterdir()), [])


class ReviewFindings(Transport):
    """Regression tests for the independent security review (F1-F7)."""

    def hostile(self, body):
        script = self.dir / "evil.py"
        script.write_text(body)
        return mock.patch.object(RR, "worker_ssh_command",
                                 lambda *a, **k: [sys.executable, str(script)])

    def head(self, size):
        return (RR.FETCH_MAGIC + json.dumps(
            {"job": {"state": "PASSED"}, "files": [{"path": "checkpoints/latest.pt", "size": size}]}
        ).encode() + b"\n")

    # F1: --dest must not reach git metadata or Claude configuration.
    def test_f1_dest_inside_git_metadata_is_refused_even_with_force(self):
        (self.repo / ".git" / "hooks").mkdir(exist_ok=True)
        for dest in (self.repo / ".git" / "hooks", self.repo / ".git" / "info"):
            dest.mkdir(exist_ok=True)
            for force in ((), ("--force",)):
                self.assertIn(".git", self.refused("checkpoints/latest.pt", "--dest", str(dest), *force).lower())
        link = self.dir / "gitlink"
        link.symlink_to(self.repo / ".git")
        self.assertIn(".git", self.refused("checkpoints/latest.pt", "--dest", str(link), "--as", "config.new").lower())
        for planted in (".git/hooks/checkpoints", ".git/config.new", ".git/info/checkpoints"):
            self.assertFalse((self.repo / planted).exists(), planted)
        self.assertFalse(any(".rr-fetch" in name for name in os.listdir(self.repo / ".git")))

    def test_f1_separate_git_directory_is_protected_by_identity_not_name(self):
        store = self.dir / "gitstore"
        other = self.dir / "other"
        git(self.dir, "init", "-q", "-b", "main", "--separate-git-dir", str(store), str(other))
        (self.work / "x.txt").write_text("x")
        os.chdir(other)
        for dest in (store, store / "hooks"):
            self.assertIn("git", self.refused("x.txt", "--dest", str(dest), "--force").lower())

    def test_f1_dest_inside_claude_configuration_needs_force(self):
        dest = self.repo / ".claude"
        dest.mkdir()
        message = self.refused("checkpoints/latest.pt", "--dest", str(dest))
        self.assertIn("--force", message)
        self.assertEqual(self.files(dest), [])

    def test_f1_config_files_that_change_behavior_need_force(self):
        for name in (".gitmodules", ".gitattributes", ".envrc"):
            (self.work / name).write_text("x")
            self.assertIn("--force", self.refused(name), name)

    # F2: a stalled runner must not hang the controller.
    def test_f2_stalled_stream_times_out_and_leaves_nothing(self):
        body = ("import sys,time\nsys.stdout.buffer.write(%r+b'ab')\nsys.stdout.buffer.flush()\n"
                "time.sleep(60)\n" % self.head(10))
        started = time.time()
        with self.hostile(body), mock.patch.object(RR, "FETCH_IDLE_TIMEOUT", 1.0), \
                mock.patch.object(RR, "FETCH_MIN_RATE", 1.0):
            message = self.refused("checkpoints/latest.pt")
        self.assertLess(time.time() - started, 15)
        self.assertIn("stalled", message)
        self.assertEqual(self.leftovers(), [])

    def test_f2_ssh_options_bound_the_connection(self):
        command = RR.worker_ssh_command("r1", "fetch", "--job", JOB, interactive=False)
        joined = " ".join(command)
        for option in ("BatchMode=yes", "ServerAliveInterval=", "ConnectTimeout="):
            self.assertIn(option, joined)
        self.assertNotIn("BatchMode", " ".join(RR.worker_ssh_command("r1", "status", "--job", JOB)))

    # F3: runner stderr is read through a bounded pipe, never an unbounded file.
    def test_f3_stderr_flood_is_bounded(self):
        body = ("import sys\nsys.stderr.write('x'*20_000_000)\nsys.stderr.flush()\nsys.exit(3)\n")
        with self.hostile(body), mock.patch.object(tempfile, "TemporaryFile") as spill:
            message = self.refused("checkpoints/latest.pt")
        spill.assert_not_called()
        self.assertLessEqual(len(message), 4200)

    # F4: termination signals must not strand staged temporary files.
    def test_f4_sigterm_and_sighup_remove_staged_files(self):
        home = self.dir / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "remotes.toml").write_text(
            '[remotes.r1]\nssh_host = "fakehost"\nworkspace_root = "%s"\nmax_jobs = 2\n' % self.ws)
        evil = self.dir / "evil2.py"
        evil.write_text("import sys,time\nsys.stdout.buffer.write(%r+b'a'*500)\nsys.stdout.buffer.flush()\n"
                        "time.sleep(60)\n" % self.head(1000))
        shim = self.dir / "bin2" / "ssh"
        shim.parent.mkdir()
        shim.write_text('#!/bin/sh\nexec %s %s\n' % (sys.executable, evil))
        shim.chmod(0o755)
        env = {**os.environ, "HOME": str(home), "PATH": f"{shim.parent}:{os.environ['PATH']}"}
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT, signal.SIGUSR1, signal.SIGUSR2):
            child = subprocess.Popen([sys.executable, "-B", str(BIN / "remote-runner"), "fetch", JOB,
                                      "checkpoints/latest.pt"], cwd=self.repo, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.time() + 15
            while time.time() < deadline and not self.leftovers():
                time.sleep(0.1)
            self.assertTrue(self.leftovers(), "the temporary file never appeared")
            child.send_signal(sig)
            child.wait(timeout=15)
            self.assertEqual(self.leftovers(), [], sig)

    # F5: the tracked-file check must hold on case-insensitive disks and fail closed.
    def test_f5_tracked_file_is_found_regardless_of_case(self):
        (self.repo / "Foo.txt").write_text("x")
        git(self.repo, "add", "Foo.txt")
        git(self.repo, "commit", "-q", "-m", "foo")
        (self.repo / "Foo.txt").unlink()
        (self.work / "foo.txt").write_text("remote")
        self.assertIn("tracked", self.refused("foo.txt"))

    def test_f5_tracked_check_survives_a_differently_cased_dest(self):
        (self.repo / "sub").mkdir()
        (self.repo / "sub" / "in.txt").write_text("x")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "sub")
        (self.repo / "sub" / "in.txt").unlink()
        (self.work / "in.txt").write_text("remote")
        variant = str(self.repo).replace("repo", "REPO")
        if not os.path.exists(variant):
            self.skipTest("case-sensitive filesystem")
        self.assertIn("tracked", self.refused("in.txt", "--dest", variant + "/sub"))

    def test_f5_a_failing_git_check_refuses_instead_of_allowing(self):
        real = subprocess.run

        def broken(argv, *a, **k):
            if isinstance(argv, list) and "ls-files" in argv:
                return subprocess.CompletedProcess(argv, 128, b"", b"")
            return real(argv, *a, **k)

        with mock.patch.object(RR.subprocess, "run", broken):
            with self.assertRaises(SystemExit):
                RR.check_fetch_target(self.repo, ["new.pt"], repo=self.repo, force=False)

    # F6: names that collide after Unicode normalisation are one name.
    def test_f6_normalisation_collisions_are_refused_before_ssh(self):
        nfc, nfd = unicodedata.normalize("NFC", "é.txt"), unicodedata.normalize("NFD", "é.txt")
        self.assertNotEqual(nfc, nfd)
        with mock.patch.object(RR, "fetch_session") as session:
            with self.assertRaises(SystemExit):
                RR.fetch_controller(RR.parser().parse_args(["fetch", JOB, nfc, nfd]))
            session.assert_not_called()

    # F7: bad input is a clean refusal, never a traceback.
    def test_f7_unencodable_path_is_a_clean_refusal(self):
        with self.assertRaises(SystemExit):
            RR.validate_fetch_path("a\udcffb")
        with self.assertRaises(SystemExit):
            RR.validate_fetch_name("a\udcffb")

    def test_f7_outside_a_repository_without_dest_is_a_clean_refusal(self):
        os.chdir(self.dir)
        message = self.refused("checkpoints/latest.pt")
        self.assertIn("--dest", message)


class SecondReviewFindings(Transport):
    """Regression tests for the re-review of the fixes (N1-N5)."""

    def hostile(self, body):
        script = self.dir / "evil.py"
        script.write_text(body)
        return mock.patch.object(RR, "worker_ssh_command",
                                 lambda *a, **k: [sys.executable, str(script)])

    def drip(self, total, slice_bytes, pause):
        header = RR.FETCH_MAGIC + json.dumps(
            {"job": {"state": "PASSED"},
             "files": [{"path": "checkpoints/latest.pt", "size": total}]}).encode() + b"\n"
        data = b"z" * total
        digest = hashlib.sha256(data).hexdigest().encode() + b"\n"
        return ("import sys,time\nw=sys.stdout.buffer\nw.write(%r);w.flush()\nd=%r\n"
                "for i in range(0,len(d),%d):\n    w.write(d[i:i+%d]);w.flush();time.sleep(%r)\n"
                "w.write(%r);w.flush()\n" % (header, data, slice_bytes, slice_bytes, pause, digest))

    # N1: progress, not chunk completion, keeps a transfer alive; a total budget bounds it.
    def test_n1_a_slow_but_progressing_stream_is_not_killed(self):
        with self.hostile(self.drip(6000, 1000, 0.5)), \
                mock.patch.object(RR, "FETCH_IDLE_TIMEOUT", 1.2), \
                mock.patch.object(RR, "FETCH_MIN_RATE", 1000.0):
            self.fetch("checkpoints/latest.pt")
        self.assertEqual((self.repo / "checkpoints" / "latest.pt").read_bytes(), b"z" * 6000)

    def test_n1_a_drip_feed_beyond_the_budget_is_killed(self):
        started = time.time()
        with self.hostile(self.drip(40000, 100, 0.05)), \
                mock.patch.object(RR, "FETCH_IDLE_TIMEOUT", 1.0), \
                mock.patch.object(RR, "FETCH_MIN_RATE", 1e9):
            message = self.refused("checkpoints/latest.pt")
        self.assertLess(time.time() - started, 10)
        self.assertIn("time budget", message)
        self.assertEqual(self.leftovers(), [])

    # N3: any dot-prefixed component is configuration-like and needs --force.
    def test_n3_dot_names_need_force_in_the_path_and_in_dest(self):
        outside = self.dir / "dest"
        (outside / ".config").mkdir(parents=True)
        (self.work / ".lfsconfig").write_text("x")
        (self.work / ".bash_profile").write_text("x")
        (self.work / "config").write_text("x")
        cases = [(".lfsconfig",), (".bash_profile", "--dest", str(outside)),
                 ("config", "--dest", str(outside / ".config"))]
        for argv in cases:
            self.assertIn("--force", self.refused(*argv), argv)
            self.fetch(*argv, "--force")

    def test_n3_ordinary_names_still_need_no_force(self):
        outside = self.dir / "dest"
        outside.mkdir()
        self.fetch("checkpoints/latest.pt", "--dest", str(outside))

    # N4: the destination's own repository decides what is tracked.
    def test_n4_tracked_files_of_another_repository_are_protected(self):
        other = self.dir / "other"
        git(self.dir, "init", "-q", "-b", "main", str(other))
        (other / "t.txt").write_text("x")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "t")
        (other / "t.txt").unlink()
        (self.work / "t.txt").write_text("remote")
        self.assertIn("tracked", self.refused("t.txt", "--dest", str(other)))

    def test_n4_a_file_where_a_tracked_directory_was_is_refused(self):
        (self.repo / "dir").mkdir()
        (self.repo / "dir" / "inner").write_text("x")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "dir")
        (self.repo / "dir" / "inner").unlink()
        (self.repo / "dir").rmdir()
        (self.work / "dir").write_text("remote")
        self.assertIn("tracked", self.refused("dir"))

    # N5: clean refusals for the remaining odd inputs.
    def test_n5_unknown_user_in_dest_is_a_clean_refusal(self):
        with self.assertRaises(SystemExit):
            self.fetch("checkpoints/latest.pt", "--dest", "~nonexistent_user_zz/x")

    def test_n5_name_length_is_counted_in_bytes(self):
        for name in ("é" * 200, "\U0001F600" * 100):
            with self.assertRaises(SystemExit, msg=len(name)):
                RR.validate_fetch_name(name)
        with self.assertRaises(SystemExit):
            RR.validate_fetch_path("d/" + "é" * 200)

    def test_n5_missing_git_is_a_clean_refusal(self):
        real = subprocess.run

        def no_git(argv, *a, **k):
            if isinstance(argv, list) and argv and argv[0] == "git":
                raise FileNotFoundError("git")
            return real(argv, *a, **k)

        with mock.patch.object(RR.subprocess, "run", no_git):
            with self.assertRaises(SystemExit):
                RR.check_fetch_target(self.repo, ["new.pt"], repo=self.repo, force=False)


class FinalReviewFindings(Transport):
    """Regression tests for the final review pass (M1, M2)."""

    # M1: a dot-named dest is not exempted just because it is a git repository.
    def test_m1_dest_that_is_a_dot_named_repository_still_needs_force(self):
        for name in (".claude", ".ssh"):
            dest = self.dir / name
            git(self.dir, "init", "-q", "-b", "main", str(dest))
            (self.work / "cfg.json").write_text("x")
            for sub in ("", "hooks"):
                target = dest / sub
                target.mkdir(exist_ok=True)
                self.assertIn("--force", self.refused("cfg.json", "--dest", str(target)), (name, sub))
            self.assertFalse((dest / "cfg.json").exists())
            self.fetch("cfg.json", "--dest", str(dest), "--force")

    # M2: a tracked file inside a nested repository is found from the outer path.
    def test_m2_tracked_file_in_a_nested_repository_is_protected(self):
        nested = self.repo / "sm"
        git(self.repo, "init", "-q", "-b", "main", str(nested))
        (nested / "t.txt").write_text("x")
        git(nested, "add", "-A")
        git(nested, "commit", "-q", "-m", "t")
        (nested / "t.txt").unlink()
        (self.work / "sm").mkdir()
        (self.work / "sm" / "t.txt").write_text("remote")
        self.assertIn("tracked", self.refused("sm/t.txt"))
        self.assertFalse((nested / "t.txt").exists())


if __name__ == "__main__":
    unittest.main()
