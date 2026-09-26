"""Tests for hooks/review_agent_guard.py, the allowlist guard for review subagents.

Run from the repository root with:  python3 -B -m unittest discover -s tests
Set GUARD to test another copy of the script (for example the installed one).

The guard is only ever asked to judge command text; nothing here executes the
judged commands.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

GUARD = Path(os.environ.get("GUARD", Path(__file__).resolve().parents[1] / "hooks" / "review_agent_guard.py"))


def run(mode, tool, cwd, **tool_input):
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(cwd)}
    return subprocess.run([sys.executable, "-B", str(GUARD), mode], input=json.dumps(payload),
                          capture_output=True, text=True)


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        # A directory shaped like the session scratchpad: /tmp/claude-<uid>/<proj>/<sess>/scratchpad
        self.scratch = base / "claude-501" / "proj" / "sess" / "scratchpad"
        self.scratch.mkdir(parents=True)
        self.repo = base / "repo"
        self.repo.mkdir()
        # The regex is anchored at /tmp, so the tests patch it through a wrapper env.
        self.env_root = base

    def bash(self, mode, command, cwd=None):
        return run(mode, "Bash", cwd or self.repo, command=command)

    def assertAllowed(self, mode, command, cwd=None):
        r = self.bash(mode, command, cwd)
        self.assertEqual(r.returncode, 0, "expected allow for %r: %s" % (command, r.stderr))

    def assertDenied(self, mode, command, cwd=None):
        r = self.bash(mode, command, cwd)
        self.assertEqual(r.returncode, 2, "expected deny for %r" % command)


class ReviewerBash(GuardCase):
    def test_allows_inspection_and_checks(self):
        for cmd in [
            "git status --short --branch",
            "git -C /some/repo status --short",
            "git -C /some/repo diff --check",
            "git diff --check",
            "git diff --cached --check",
            "git log --oneline -n 5",
            "git show HEAD:calc.py",
            "git stash list",
            "git branch -a",
            "git config --get remote.origin.url",
            "ls -la && cat calc.py | head -20",
            "rg -n 'len\\(xs\\)' . 2>&1",
            "grep -n foo file 2>/dev/null",
            "rg -n pattern src",
            "find . -name '*.py' -maxdepth 2",
            "sed -n '1,20p' calc.py",
            "sort -u names.txt",
            "python3 -B -m unittest discover -s tests",
            "python3 -B -m pytest -p no:cacheprovider -q",
            "make -n test",
            "cd sub && git status",
        ]:
            with self.subTest(cmd=cmd):
                self.assertAllowed("reviewer", cmd)

    def test_denies_the_observed_python_heredoc_write(self):
        cmd = ("python3 - <<'E'\ns = open('calc.py').read().replace('a', 'b')\n"
               "open('calc.py', 'w').write(s)\nE")
        self.assertDenied("reviewer", cmd)

    def test_denies_writes_and_execution(self):
        for cmd in [
            "python3 -c \"open('calc.py','w').write('x')\"",
            "python3 -m unittest",  # no -B
            "python3 -B calc.py",
            "python3 -B -m pytest",  # cache write
            "python3 -B -m http.server",
            "echo x > calc.py",
            "echo x >> calc.py",
            "cat a &> out",
            "cat a | tee out",
            "sed -i s/a/b/ calc.py",
            "sed -n 'w out' calc.py",
            "sed -e 1d calc.py",
            "rm calc.py",
            "mv a b",
            "cp a b",
            "touch x",
            "mkdir x",
            "chmod +x a",
            "git commit -m x",
            "git add .",
            "git stash",
            "git stash pop",
            "git reset --hard",
            "git checkout -- calc.py",
            "git restore calc.py",
            "git push",
            "git fetch",
            "git clone /a /b",
            "git -C /x commit -m x",
            "git -C /x -c core.pager=sh log",
            "git -C /x push",
            "git -C /x init",
            "git -C /x",
            "git -c core.pager=sh log",
            "git diff --output=out",
            "git log --output=out",
            "git config user.name x",
            "git branch newbranch",
            "git branch -D main",
            "git tag v1",
            "git grep -O sh foo",
            "curl http://example.com",
            "ssh host",
            "sh script.sh",
            "bash -c ls",
            "env ls",
            "xargs rm",
            "awk 'BEGIN{system(\"id\")}'",
            "find . -delete",
            "find . -exec rm {} ;",
            "find . -fprint out",
            "sort -o out in",
            "sort -uo out in",
            "sort --output=out in",
            "rg --pre sh x",
            "tail -f log",
            "make -f evil.mk",
            "make -C /elsewhere",
            "./run.sh",
            "/bin/ls",
            "FOO=1 ls",
        ]:
            with self.subTest(cmd=cmd):
                self.assertDenied("reviewer", cmd)

    def test_denies_shell_tricks(self):
        for cmd in [
            "ls; rm calc.py",
            "ls && rm calc.py",
            "ls || rm calc.py",
            "ls | rm calc.py",
            "ls\nrm calc.py",
            "ls $(rm calc.py)",
            "ls `rm calc.py`",
            "ls \"$(rm calc.py)\"",
            "cat <(ls)",
            "(rm calc.py)",
            "ls & rm calc.py",
            "cat $HOME/x",
            "cat \"$HOME/x\"",
            "echo {a,b}",
            "ls # comment",
            "cat 'unterminated",
            "cat a |& rm b",
        ]:
            with self.subTest(cmd=cmd):
                self.assertDenied("reviewer", cmd)

    def test_credential_reads_are_denied_but_ordinary_patterns_are_not(self):
        for cmd in ["cat .env", "cat ./.env.local", "head -5 .env", "grep token ~/.ssh/config",
                    "sed -n '1,5p' server.pem", "sort .env", "diff .env .env.example", "cat ~/.aws/credentials",
                    "git show HEAD:.env", "git diff -- .env", "git log -p -- config/id_rsa",
                    "grep -rn token .", "grep -R token src", "grep -irn token src", "grep --recursive x .",
                    "grep -d recurse x .", "rg --hidden token", "rg -uu token", "rg -. token",
                    "rg --no-ignore token", "rg -g '.env*' token", "rg --glob=.env token",
                    "rg -g'*.pem' token", "rg token ~/.ssh", "cat ~/.netrc"]:
            with self.subTest(cmd=cmd):
                self.assertDenied("reviewer", cmd)
        for cmd in ["grep -n credentials src/app.py", "rg -n 'secret_key' src", "rg -g '*.py' token",
                    "git log --grep=credentials", "git show HEAD:src/app.py", "git diff -- src/app.py",
                    "grep -n '\\.env' README.md"]:
            with self.subTest(cmd=cmd):
                self.assertAllowed("reviewer", cmd)

    def test_quoted_metacharacters_are_data(self):
        for cmd in [
            "grep -n 'a;b' file",
            "grep -n 'a|b' file",
            "grep -n 'a > b' file",
            "grep -n \"a && b\" file",
            "sed -n '$p' file",
            "grep -n 'x$' file",
        ]:
            with self.subTest(cmd=cmd):
                self.assertAllowed("reviewer", cmd)

    def test_write_tools_refused_and_bad_input_fails_closed(self):
        self.assertEqual(run("reviewer", "Write", self.repo, file_path=str(self.repo / "a")).returncode, 2)
        self.assertEqual(run("reviewer", "Edit", self.repo, file_path=str(self.repo / "a")).returncode, 2)
        bad = subprocess.run([sys.executable, "-B", str(GUARD), "reviewer"], input="not json",
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        empty = subprocess.run([sys.executable, "-B", str(GUARD), "nonsense"], input="{}",
                               capture_output=True, text=True)
        self.assertEqual(empty.returncode, 2)


class ResearchMode(GuardCase):
    def call(self, tool, **tool_input):
        return run("research", tool, self.repo, **tool_input).returncode

    def test_ordinary_lookups_are_allowed(self):
        self.assertEqual(self.call("Read", file_path=str(self.repo / "Cargo.toml")), 0)
        self.assertEqual(self.call("Grep", pattern="version", path=str(self.repo / "src")), 0)
        self.assertEqual(self.call("Glob", pattern="**/*.toml"), 0)
        self.assertEqual(self.call("WebFetch", url="https://docs.python.org/3/library/shlex.html?highlight=shlex",
                                   prompt="quoting rules"), 0)
        self.assertEqual(self.call("WebSearch", query="python 3.13 shlex punctuation_chars"), 0)

    def test_credential_paths_are_refused(self):
        home = Path.home()
        for path in [str(self.repo / ".env"), str(self.repo / ".env.local"), str(home / ".ssh" / "config"),
                     str(home / ".aws" / "credentials"), str(self.repo / "server.pem"), str(self.repo / "a.key"),
                     str(home / ".netrc"), str(self.repo / "id_rsa"), ".env", "../.env",
                     str(self.repo / "terraform.tfstate")]:
            with self.subTest(path=path):
                self.assertEqual(self.call("Read", file_path=path), 2)
        self.assertEqual(self.call("Grep", pattern="x", path=str(home / ".ssh")), 2)
        self.assertEqual(self.call("Grep", pattern="x", path=str(home / ".aws")), 2)

    def test_exfiltration_shaped_fetches_and_searches_are_refused(self):
        for url in ["http://docs.python.org/x", "https://user:pw@example.com/x", "ftp://example.com/x",
                    "https://example.com/?d=" + "A" * 201, "https://example.com/#" + "B" * 201,
                    "https://example.com/" + "c" * 600, "file:///etc/passwd", "", "example.com/x"]:
            with self.subTest(url=url[:40]):
                self.assertEqual(self.call("WebFetch", url=url), 2)
        self.assertEqual(self.call("WebSearch", query="q " * 101), 2)

    def test_other_tools_are_refused(self):
        self.assertEqual(self.call("Bash", command="ls"), 2)
        self.assertEqual(self.call("Write", file_path=str(self.repo / "a")), 2)


class SecurityMode(GuardCase):
    """The scratch regex is anchored at /tmp, so these tests use the real /tmp layout."""

    def setUp(self):
        super().setUp()
        self.real = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path("/tmp")
        self.sp = self.real / ("claude-%d" % os.getuid()) / "guardtest" / ("s%d" % os.getpid()) / "scratchpad"
        self.sp.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        # Remove only what this test created, deepest first, without shell rm.
        for p in sorted(self.sp.rglob("*"), key=lambda q: len(q.parts), reverse=True):
            p.rmdir() if p.is_dir() and not p.is_symlink() else p.unlink()
        for d in (self.sp, self.sp.parent, self.sp.parent.parent):
            try:
                d.rmdir()
            except OSError:
                pass

    def test_scratch_writes_allowed(self):
        s = str(self.sp)
        for tool_input in ({"file_path": s + "/note.md"}, {"file_path": s + "/a/b/fake_ssh"}):
            with self.subTest(tool_input=tool_input):
                self.assertEqual(run("security", "Write", self.repo, **tool_input).returncode, 0)
                self.assertEqual(run("security", "Edit", self.repo, **tool_input).returncode, 0)
        for cmd in [
            "mkdir -p %s/x/y" % s,
            "cp -R . %s/copy" % s,
            "touch %s/f" % s,
            "chmod +x %s/f" % s,
            "mv %s/f %s/g" % (s, s),
            "git init -q %s/repo" % s,
            "git -C %s/repo add -A" % s,
            "git -C %s/repo commit -qm base" % s,
            "git clone -q . %s/clone" % s,
            "python3 -B %s/probe.py" % s,
            "sh %s/run.sh" % s,
            "env PATH=%s/bin:/usr/bin:/bin python3 -B %s/probe.py" % (s, s),
            "env PYTHONPATH=%s python3 -B -m unittest" % s,
            "git status",
            "git -C %s status" % self.repo,
            "python3 -B -m unittest",
        ]:
            with self.subTest(cmd=cmd):
                self.assertAllowed("security", cmd)

    def test_writes_outside_scratch_denied(self):
        s = str(self.sp)
        for tool_input in ({"file_path": str(self.repo / "a.py")},
                           {"file_path": s + "/../escape.txt"},
                           {"file_path": "relative.txt"},
                           {"file_path": ""}):
            with self.subTest(tool_input=tool_input):
                self.assertEqual(run("security", "Write", self.repo, **tool_input).returncode, 2)
        (self.sp / "link").symlink_to(self.repo)
        self.assertEqual(run("security", "Write", self.repo, file_path=s + "/link/a.py").returncode, 2)
        for cmd in [
            "mkdir %s/x" % self.repo,
            "cp calc.py %s/calc.py" % self.repo,
            "cp calc.py %s/../x" % s,
            "cp -t %s a b" % self.repo,
            "cp a %s/*" % s,
            "touch %s" % (self.repo / "f"),
            "chmod +x %s/f" % self.repo,
            "mv %s/f %s/f" % (s, self.repo),
            "git init %s/x" % self.repo,
            "git init",
            "git -C %s commit -qm x" % self.repo,
            "git -C %s push" % s,
            "git clone https://example.com/x.git %s/c" % s,
            "git clone git@example.com:x.git %s/c" % s,
            "git clone . %s/../c" % s,
            "python3 -B %s/link/evil.py" % s,
            "python3 -B evil.py",
            "python3 -B -c pass",
            "sh evil.sh",
            "env",
            "env PATH=/x",
            "env -i python3 -B evil.py",
            "env PATH=/x sh -c id",
            "env PATH=/x python3 -B evil.py",
            "env PATH=/x rm f",
            "bash -c ls",
            "cat x > %s/f" % s,
            "rm %s/f" % s,
            "curl http://example.com",
        ]:
            with self.subTest(cmd=cmd):
                self.assertDenied("security", cmd)


if __name__ == "__main__":
    unittest.main()
