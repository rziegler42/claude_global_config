"""Regression tests for findings from the security review of the agent guard.

Run from the repository root with:  python3 -B -m unittest discover -s tests

The guard only judges command text and tool calls; nothing here executes them.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = Path(os.environ.get("GUARD", ROOT / "hooks" / "review_agent_guard.py"))


SESSION = "s%d" % os.getpid()


def decide(mode, tool, cwd, session=SESSION, **tool_input):
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(cwd)}
    if session:
        payload["session_id"] = session
    return subprocess.run([sys.executable, "-B", str(GUARD), mode], input=json.dumps(payload),
                          capture_output=True, text=True).returncode


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".env").write_text("TOKEN=abc\n")
        (self.repo / "calc.py").write_text("print(1)\n")
        (self.repo / "notes.txt").write_text("hello\n")
        self.scratch = base / "claude-501" / "proj" / "sess" / "scratchpad"
        self.scratch.mkdir(parents=True)

    def bash(self, mode, command, cwd=None):
        return decide(mode, "Bash", cwd or self.repo, command=command)

    def deny(self, command, mode="reviewer"):
        self.assertEqual(self.bash(mode, command), 2, "expected deny: %r" % command)

    def allow(self, command, mode="reviewer"):
        self.assertEqual(self.bash(mode, command), 0, "expected allow: %r" % command)


class ReadToolsAreGuardedInEveryMode(Guard):
    def test_read_glob_grep_check_credentials_in_all_modes(self):
        for mode in ("reviewer", "security", "research"):
            with self.subTest(mode=mode):
                self.assertEqual(decide(mode, "Read", self.repo, file_path=str(self.repo / ".env")), 2)
                self.assertEqual(decide(mode, "Read", self.repo, file_path=str(self.repo / "calc.py")), 0)
                self.assertEqual(decide(mode, "Glob", self.repo, pattern=".e*", path=str(self.repo)), 2)
                self.assertEqual(decide(mode, "Grep", self.repo, pattern="x", path=".", glob=".env"), 2)
                self.assertEqual(decide(mode, "Grep", self.repo, pattern="x", path="."), 0)

    def test_agent_frontmatter_attaches_the_hook_to_the_read_tools(self):
        for name in ("workflow-reviewer", "security-reviewer", "technical-researcher"):
            text = (ROOT / "agents" / ("%s.md" % name)).read_text()
            line = next(l for l in text.splitlines() if "matcher:" in l)
            for tool in ("Read", "Glob", "Grep", "Bash"):
                if name == "technical-researcher" and tool == "Bash":
                    continue
                self.assertIn(tool, line, "%s matcher %r" % (name, line))


class GlobbedReadArguments(Guard):
    def test_globs_cannot_name_credential_files(self):
        for cmd in ("cat .e*", "cat .en?", "cat .e[n]v", "rg x .e*",
                    "git diff --no-index /dev/null .e*"):
            self.deny(cmd)

    def test_unquoted_globs_are_refused_and_quoted_patterns_still_work(self):
        for cmd in ("cat *.py", "ls *.txt", "cat .e[^x]v", "cat .e[[:alpha:]]v", "cat .e?v"):
            self.deny(cmd)
        self.allow("rg 'def .*' calc.py")
        self.allow("git grep -n 'x.*y'")
        self.allow("find . -name '*.py' -maxdepth 2")


class GitGrepPagerExecution(Guard):
    def test_open_files_in_pager_in_every_spelling_is_refused(self):
        for cmd in ("git grep -Otouch l1", "git grep -O'sh -c x --' l1",
                    "git grep --open-files-in-pager='touch p;' l1", "git grep --open-files l1",
                    "git grep --open l1", "git grep -nOtouch l1"):
            self.deny(cmd)

    def test_ordinary_git_grep_works(self):
        self.allow("git grep -n foo")
        self.allow("git grep --only-matching foo")


class RedirectBoundaries(Guard):
    def test_fd_redirect_prefix_cannot_name_a_file(self):
        for cmd in ("echo hi >&2x", "echo hi 2>&1x", "echo PAYLOAD >&2x", "echo hi >/dev/nullx",
                    "echo hi 2>/dev/null9"):
            self.deny(cmd)

    def test_real_fd_redirects_still_work(self):
        for cmd in ("echo hi >&2", "echo hi 2>&1", "grep x notes.txt 2>/dev/null", "ls >/dev/null 2>&1",
                    "echo hi >&2 && echo ok"):
            self.allow(cmd)


class AbbreviatedOptions(Guard):
    def test_sort_cannot_write_or_run_programs(self):
        for cmd in ("sort --out=/tmp/x notes.txt", "sort --outp=/tmp/x notes.txt",
                    "sort --comp=sh notes.txt", "sort --output=/tmp/x notes.txt", "sort -o /tmp/x notes.txt",
                    "sort -T /tmp notes.txt", "sort -S 1 notes.txt"):
            self.deny(cmd)
        self.allow("sort -u notes.txt")
        self.allow("sort -nr notes.txt")
        self.allow("sort -k 2,2 notes.txt")

    def test_grep_cannot_recurse_in_any_spelling(self):
        for cmd in ("grep -r x .", "grep --recurs x .", "grep --rec x .", "grep -d rec x .",
                    "grep --directories=rec x .", "grep -R x .", "grep --dereference-recursive x .",
                    "grep -f .env notes.txt", "grep --file=.env notes.txt"):
            self.deny(cmd)
        self.allow("grep -n foo notes.txt")
        self.allow("grep -inw foo notes.txt")
        self.allow("grep -e foo -e bar notes.txt")

    def test_diff_cannot_recurse(self):
        for cmd in ("diff -r . /x", "diff --recursive . /x", "diff --recurs . /x", "diff -rq a b"):
            self.deny(cmd)
        self.allow("diff -u calc.py notes.txt")

    def test_tail_cannot_follow_in_any_spelling(self):
        for cmd in ("tail -f x", "tail -F x", "tail -qf x", "tail --fol x", "tail --follow x", "tail --retry x"):
            self.deny(cmd)
        self.allow("tail -n 20 notes.txt")
        self.allow("tail -20 notes.txt")

    def test_file_cannot_write_a_magic_database(self):
        self.deny("file -C -m x")
        self.deny("file -m x notes.txt")
        self.allow("file calc.py")

    def test_sed_extra_flags_are_refused(self):
        self.deny("sed -n 1p -i notes.txt")
        self.deny("sed -n 1p -f script notes.txt")
        self.allow("sed -n '1,5p' notes.txt")


class CredentialPaths(Guard):
    def test_directory_names_are_case_insensitive(self):
        home = self.repo / ".SSH"
        home.mkdir()
        (home / "id_rsa").write_text("x")
        for name in (".SSH/id_rsa", ".Kube/config", ".AWS/credentials", ".DOCKER/config.json"):
            self.deny("cat %s" % name)

    def test_more_credential_locations(self):
        names = (".credentials.json", "prod.env", "app.env", "terraform.tfvars", "vault.kdbx",
                 ".bash_history", ".zsh_history", ".config/gh/hosts.yml", ".git/config",
                 ".codex/auth.json", "Library/Keychains/login.keychain-db", ".seal-key")
        for name in names:
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("secret\n")
        for name in (".credentials.json", "prod.env", "app.env", "terraform.tfvars", "vault.kdbx",
                     ".bash_history", ".zsh_history", ".config/gh/hosts.yml", ".git/config",
                     ".codex/auth.json", "Library/Keychains/login.keychain-db", ".seal-key"):
            self.deny("cat %s" % name)

    def test_proc_environ_is_refused(self):
        self.deny("cat /proc/self/environ")
        self.deny("head /proc/1/environ")


class RunnersCannotWrite(Guard):
    def test_make_options_that_change_what_runs_or_where_are_refused(self):
        for cmd in ("make -sf Makefile", "make -f other", "make -C /x", "make -I /x", "make --eval=x",
                    "make -o target"):
            self.deny(cmd)
        self.allow("make test")
        self.allow("make -n test")
        self.allow("make -j4 test")

    def test_pytest_output_and_config_options_are_refused(self):
        base = "python3 -B -m pytest -p no:cacheprovider"
        for extra in ("--junitxml=/tmp/x.xml", "--junit-xml=/tmp/x.xml", "--basetemp=/x", "-o cache_dir=/x",
                      "-c /x/pytest.ini", "--rootdir=/x", "-p other", "--log-file=/x", "--result-log=/x"):
            self.deny("%s %s" % (base, extra))
        self.allow("%s tests/test_x.py" % base)
        self.allow("%s -q -x" % base)


class SecurityModeScratchWrites(Guard):
    """The scratch pattern is anchored at /tmp, so these tests use the real /tmp layout."""

    def setUp(self):
        super().setUp()
        self.real = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path("/tmp")
        self.session = "s%d" % os.getpid()
        self.sp = self.real / ("claude-%d" % os.getuid()) / "guardtest-review" / self.session / "scratchpad"
        self.other = self.sp.parent.parent / (self.session + "x") / "scratchpad"
        for directory in (self.sp, self.other):
            directory.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for directory in (self.sp, self.other):
            for path in sorted(directory.rglob("*"), reverse=True):
                path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
        for path in (self.sp, self.sp.parent, self.other, self.other.parent):
            try:
                path.rmdir()
            except OSError:
                pass
        try:
            self.sp.parent.parent.rmdir()
        except OSError:
            pass

    def test_cp_sources_are_checked_for_credentials(self):
        dest = self.sp / "x"
        self.assertEqual(self.bash("security", "cp %s %s" % (self.repo / ".env", dest)), 2)
        self.assertEqual(self.bash("security", "cp -rt /etc %s" % dest), 2)
        self.assertEqual(self.bash("security", "cp %s %s" % (self.repo / "calc.py", dest)), 0)

    def test_chmod_mode_must_be_a_mode(self):
        target = self.sp / "x"
        self.assertEqual(self.bash("security", "chmod -x /etc/hosts %s" % target), 2)
        self.assertEqual(self.bash("security", "chmod +x %s" % target), 0)
        self.assertEqual(self.bash("security", "chmod 755 %s" % target), 0)

    def test_git_clone_runs_no_program_flags(self):
        dest = self.sp / "d"
        for flag in ("--upload-pack=touch", "-u touch", "--config=core.x=y", "--template=/x", "--reference=/x"):
            self.assertEqual(self.bash("security", "git clone --no-local %s %s %s" % (flag, self.repo, dest)), 2)

    def test_scratchpad_is_bound_to_the_session(self):
        mine, other = self.sp / "y", self.other / "y"
        self.assertEqual(decide("security", "Write", self.repo, session=self.session, file_path=str(mine)), 0)
        self.assertEqual(decide("security", "Write", self.repo, session=self.session, file_path=str(other)), 2)
        self.assertEqual(decide("security", "Bash", self.repo, session=self.session,
                                command="cp %s %s" % (self.repo / "calc.py", other)), 2)
        self.assertEqual(decide("security", "Bash", self.repo, session=self.session,
                                command="cp %s %s" % (self.repo / "calc.py", mine)), 0)


class ResearchMode(Guard):
    def test_webfetch_rejects_internal_and_exfiltration_shaped_urls(self):
        for url in ("https://169.254.169.254/latest/meta-data", "https://localhost/x", "https://127.0.0.1/x",
                    "https://10.0.0.5/x", "https://printer.local/x", "https://intranet/x",
                    "https://%s.example.com/x" % ("a" * 60), "https://docs.example.com/%s" % ("p" * 400)):
            self.assertEqual(decide("research", "WebFetch", self.repo, url=url), 2, url)
        self.assertEqual(decide("research", "WebFetch", self.repo, url="https://docs.python.org/3/library/os.html"), 0)


HEAD = "a" * 40


class CommitterMode(Guard):
    """safe-committer: read-only inspection plus exactly `claude-workflow commit`."""

    def test_the_documented_commit_command_is_allowed(self):
        self.allow("claude-workflow commit --expected-head %s --subject 'Update a' -- calc.py" % HEAD, "committer")
        self.allow("claude-workflow commit --expected-head %s --subject 'Update a' --body 'Why.' "
                   "--trailer 'Reviewed-by: Pat <p@example.com>' --leave-other-staged -- calc.py notes.txt"
                   % HEAD, "committer")

    def test_inspection_is_allowed(self):
        for command in ("git status --short --branch", "git diff --cached --name-only", "git log -n 3 --oneline",
                        "git rev-parse HEAD", "git diff -- calc.py", "ls -la"):
            self.allow(command, "committer")

    def test_everything_else_is_refused(self):
        refused = (
            "claude-workflow commit --expected-head %s --subject x -- ." % HEAD,
            "claude-workflow commit --expected-head %s --subject x -- '*.py'" % HEAD,
            "claude-workflow commit --expected-head %s --subject x -- ':/'" % HEAD,
            "claude-workflow commit --expected-head %s --subject x -- -evil" % HEAD,
            "claude-workflow commit --expected-head %s --subject x --no-verify -- calc.py" % HEAD,
            "claude-workflow commit --expected-head notahash --subject x -- calc.py",
            "claude-workflow commit --subject x -- calc.py",
            "claude-workflow commit --expected-head %s -- calc.py" % HEAD,
            "claude-workflow commit --expected-head %s --subject x" % HEAD,
            "claude-workflow remove --confirm calc.py",
            "claude-workflow amend-message --expected-head %s --subject x" % HEAD,
            "claude-workflow graph-finalize",
            "git commit -m x", "git push", "git add calc.py", "git reset --hard", "git stash",
            "claude-workflow commit --expected-head %s --subject x -- calc.py; git push" % HEAD,
            "claude-workflow commit --expected-head %s --subject x -- calc.py && git push" % HEAD,
            "cp calc.py /tmp/x", "rm calc.py",
        )
        for command in refused:
            self.deny(command, "committer")

    def test_other_modes_do_not_gain_the_commit_command(self):
        for mode in ("reviewer", "security", "research"):
            self.deny("claude-workflow commit --expected-head %s --subject x -- calc.py" % HEAD, mode)

    def test_write_tools_and_secret_reads_are_refused(self):
        self.assertEqual(decide("committer", "Write", self.repo, file_path=str(self.repo / "a")), 2)
        self.assertEqual(decide("committer", "Edit", self.repo, file_path=str(self.repo / "a")), 2)
        self.assertEqual(decide("committer", "Read", self.repo, file_path=str(self.repo / ".env")), 2)
        self.assertEqual(decide("committer", "Read", self.repo, file_path=str(self.repo / "calc.py")), 0)

    def test_agent_frontmatter_attaches_the_committer_hook(self):
        text = (ROOT / "agents" / "safe-committer.md").read_text()
        self.assertIn("review_agent_guard.py", text)
        line = next(l for l in text.splitlines() if "matcher:" in l)
        for tool in ("Bash", "Read", "Glob", "Grep"):
            self.assertIn(tool, line)
        self.assertTrue(text.rstrip().splitlines()[0] == "---")
        self.assertRegex(text, r"review_agent_guard\.py\" committer")


class ChunkMode(Guard):
    """graphify-semantic: write one graphify-out/.graphify_chunk_NN.json, read sources."""

    def setUp(self):
        super().setUp()
        (self.repo / "graphify-out").mkdir()

    def write(self, path, tool="Write"):
        return decide("chunk", tool, self.repo, file_path=str(path))

    def test_only_a_chunk_file_directly_under_graphify_out_may_be_written(self):
        for tool in ("Write", "Edit"):
            self.assertEqual(self.write(self.repo / "graphify-out" / ".graphify_chunk_03.json", tool), 0)
            self.assertEqual(self.write("graphify-out/.graphify_chunk_12.json", tool), 0)
        denied = (
            self.repo / "calc.py", self.repo / "graphify-out" / "graph.json",
            self.repo / "graphify-out" / ".graphify_chunks.json",
            self.repo / "graphify-out" / ".graphify_chunk_x.json",
            self.repo / "graphify-out" / "sub" / ".graphify_chunk_01.json",
            self.repo / ".graphify_chunk_01.json",
            self.repo / "graphify-out" / ".graphify_chunk_01.json.bak",
            self.repo.parent / "graphify-out" / ".graphify_chunk_01.json",
            "../graphify-out/.graphify_chunk_01.json", "graphify-out/../calc.py", "/etc/passwd", "",
        )
        for path in denied:
            with self.subTest(path=str(path)):
                self.assertEqual(self.write(path), 2)

    def test_a_symlinked_output_directory_or_file_is_refused(self):
        outside = self.repo.parent / "outside"
        outside.mkdir()
        (self.repo / "graphify-out" / ".graphify_chunk_05.json").symlink_to(outside / "x.json")
        self.assertEqual(self.write(self.repo / "graphify-out" / ".graphify_chunk_05.json"), 2)
        (self.repo / "graphify-out").rmdir() if not list((self.repo / "graphify-out").iterdir()) else None
        for child in (self.repo / "graphify-out").iterdir():
            child.unlink()
        (self.repo / "graphify-out").rmdir()
        (self.repo / "graphify-out").symlink_to(outside)
        self.assertEqual(self.write(self.repo / "graphify-out" / ".graphify_chunk_06.json"), 2)

    def test_reads_are_checked_and_everything_else_is_refused(self):
        self.assertEqual(decide("chunk", "Read", self.repo, file_path=str(self.repo / "calc.py")), 0)
        self.assertEqual(decide("chunk", "Read", self.repo, file_path=str(self.repo / ".env")), 2)
        for tool, args in (("Bash", {"command": "ls"}), ("Glob", {"pattern": "*.py"}),
                           ("Grep", {"pattern": "x"}), ("WebFetch", {"url": "https://docs.python.org/"}),
                           ("NotebookEdit", {"notebook_path": "x.ipynb"})):
            self.assertEqual(decide("chunk", tool, self.repo, **args), 2, tool)

    def test_agent_frontmatter_attaches_the_chunk_hook(self):
        text = (ROOT / "agents" / "graphify-semantic.md").read_text()
        line = next(l for l in text.splitlines() if "matcher:" in l)
        for tool in ("Read", "Write", "Edit"):
            self.assertIn(tool, line)
        self.assertRegex(text, r"review_agent_guard\.py\" chunk")


class ThirdReview(Guard):
    """Fixes from the second independent review of the guard."""

    def test_cd_into_a_credential_directory_is_refused(self):
        ssh = self.repo / ".ssh"
        ssh.mkdir()
        (ssh / "id_rsa").write_text("key\n")
        for cmd in ("cd .s* && cat id_rsa", "cd .ss[h]; cat id_rsa", "cd .ssh && cat id_rsa", "cd ~/.ssh && ls"):
            self.deny(cmd)
        self.allow("cd %s && ls" % self.repo)

    def test_git_cannot_reach_untracked_or_ignored_secrets(self):
        for cmd in ("git grep --no-index --no-exclude-standard -e API_KEY", "git grep --no-index -e KEY",
                    "git grep --untracked -e KEY", "git -C ~/.ssh grep -e BEGIN",
                    "git -C %s grep -e x" % (self.repo / ".ssh"), "git -C ~/.aws log"):
            self.deny(cmd)
        self.allow("git grep -n foo")
        self.allow("git -C %s status --short" % self.repo)

    def test_git_pathspecs_cannot_wildcard_into_secret_files(self):
        for cmd in ("git log -p -- '*nv'", "git show HEAD -- '.e[n]v'", "git grep -e KEY -- '*nv'",
                    "git log -p -- ':(glob)**/.env'", "git diff -- ':/.env'"):
            self.deny(cmd)
        self.allow("git log -p -- calc.py")
        self.allow("git diff -- calc.py notes.txt")

    def test_raw_blob_reads_are_refused_but_revision_paths_work(self):
        self.deny("git cat-file -p 0123456789abcdef0123456789abcdef01234567")
        self.deny("git cat-file blob 0123456789abcdef0123456789abcdef01234567")
        self.allow("git cat-file -t HEAD")
        self.allow("git show HEAD:calc.py")
        self.deny("git show HEAD:.env")

    def test_git_config_only_reads_a_single_named_key(self):
        for cmd in ("git config --get --file ~/.pypirc pypi.password", "git config --get --blob HEAD:x a.b",
                    "git config --list", "git config --get-regexp .", "git config --get credential.helper",
                    "git config --get user.password",
                    "git config --get --includes core.editor"):
            self.deny(cmd)
        self.allow("git config --get core.autocrlf")
        self.allow("git config --get user.name")

    def test_repository_config_that_runs_programs_blocks_git(self):
        config = self.repo / ".git"
        config.mkdir()
        (config / "config").write_text("[core]\n\tfsmonitor = /tmp/evil.sh\n")
        for cmd in ("git status", "git diff", "git log -p"):
            self.deny(cmd)
        (config / "config").write_text("[core]\n\trepositoryformatversion = 0\n")
        self.allow("git status --short")

    def test_diff_of_directories_is_refused(self):
        other = self.repo.parent / "other"
        other.mkdir()
        (other / ".env").write_text("TOKEN=zzz\n")
        self.deny("diff %s %s" % (self.repo, other))
        self.allow("diff -u calc.py notes.txt")

    def test_glob_and_grep_tools_see_through_wildcard_spellings(self):
        for pattern in ("**/.env", "{.env,x}", ".e[^x]v", ".e[[:alpha:]]v", "**/.ssh/id_rsa", ".s*/id_rsa",
                        "**/.git/config", "**/.aws/credentials", "!(x)", "*.env"):
            with self.subTest(tool="Glob", pattern=pattern):
                self.assertEqual(decide("reviewer", "Glob", self.repo, pattern=pattern), 2)
            with self.subTest(tool="Grep", glob=pattern):
                self.assertEqual(decide("reviewer", "Grep", self.repo, pattern="KEY", glob=pattern), 2)
        for home in (str(Path.home()), "~", "/"):
            self.assertEqual(decide("reviewer", "Grep", self.repo, pattern="KEY", path=home), 2)
        self.assertEqual(decide("reviewer", "Glob", self.repo, pattern="**/*.py"), 0)
        self.assertEqual(decide("reviewer", "Grep", self.repo, pattern="KEY", glob="*.py", path="."), 0)

    def test_legitimate_search_patterns_are_not_mistaken_for_paths(self):
        for cmd in ("grep '.env' notes.txt", "grep -n 'api.key' notes.txt", "git grep -n '.env'",
                    "git log --grep=.env", "echo '.env is ignored'", "grep -n \"foo$\" notes.txt",
                    "grep -n '\\$(' notes.txt", "sort -nk2 notes.txt", "diff -- calc.py notes.txt",
                    "rg '.env' ."):
            self.allow(cmd)

    def test_substitutions_in_double_quotes_are_still_refused(self):
        for cmd in ('echo "$(id)"', 'echo "`id`"', 'echo "$HOME"', 'echo "${HOME}"', "echo $(id)",
                    "echo `id`"):
            self.deny(cmd)

    def test_session_binding_fails_closed_without_a_session_id(self):
        self.assertEqual(decide("security", "Write", self.repo, session=None,
                                file_path="/private/tmp/claude-501/p/s/scratchpad/x"), 2)

    def test_cp_and_mv_accept_only_known_flags(self):
        for cmd in ("cp --tar=/etc a b", "cp --ta=/etc a b", "mv -ft/etc a b", "mv --tar=/etc a b",
                    "cp -S x a b", "cp --suffix=x a b"):
            self.assertEqual(self.bash("security", cmd), 2, cmd)

    def test_research_urls_reject_ipv4_shorthand_and_odd_internal_names(self):
        for url in ("https://0x7f.1/", "https://0177.0.0.1/", "https://127.1/", "https://127.0.1/",
                    "https://169.254.43518/", "https://wiki.intranet/x", "https://box.test/x",
                    "https://svc.corp/x", "https://127.0.0.1.nip.io.localhost/x"):
            self.assertEqual(decide("research", "WebFetch", self.repo, url=url), 2, url)
        self.assertEqual(decide("research", "WebSearch", self.repo, query=["a" * 5000]), 2)

    def test_pytest_and_make_stay_inside_their_lane(self):
        self.deny("python3 -B -m pytest no:cacheprovider")
        self.deny("python3 -B -m pytest -p no:cacheprovider --pastebin=all")
        self.deny("python3 -B -m pytest -p no:cacheprovider --doctest-modules")
        self.deny("make clean")
        self.deny("make deploy")
        self.deny("make SHELL=/bin/sh test")
        self.allow("make test")
        self.allow("make -n deploy")


class FourthReview(Guard):
    """Fixes from the third independent review of the guard."""

    def test_git_grep_pattern_flags_do_not_hide_a_path(self):
        for cmd in ("git grep -eSECRET .env", "git grep -f pat.txt .env", "git grep -fpat.txt .env",
                    "git grep -iex .env", "git grep -e x .env"):
            self.deny(cmd)
        self.allow("git grep -n '.env'")
        self.allow("git grep -e '.env' -- calc.py")

    def test_rg_pattern_file_spellings_do_not_hide_a_path(self):
        for cmd in ("rg --file=pat.txt .env", "rg -fpat.txt untracked.env", "rg -f pat.txt .env",
                    "rg --file pat.txt .env", "rg --files .env", "rg -e x .env", "rg x .env"):
            self.deny(cmd)
        self.allow("rg '.env' .")

    def test_rg_globs_cannot_override_hidden_and_ignore_rules(self):
        for cmd in ("rg -g '.e?v' SECRET", "rg -g '.*' SECRET", "rg -g '.e*' SECRET", "rg -g '*' TOKEN",
                    "rg --glob=.e?v SECRET", "rg --iglob '*' TOKEN", "rg -g '*.env' x"):
            self.deny(cmd)
        self.allow("rg -g '*.py' def")
        self.allow("rg -g 'src/*.py' def")
        self.allow("rg -g '!*.min.js' def")

    def test_arithmetic_expansion_in_double_quotes_is_refused(self):
        for cmd in ('echo "$[FOO]"', 'echo "$[1+1]"'):
            self.deny(cmd)
        self.allow('echo "a$"')

    def test_stash_show_checks_repository_config(self):
        config = self.repo / ".git"
        config.mkdir()
        (config / "config").write_text("[diff \"x\"]\n\ttextconv = /tmp/evil.sh\n")
        for cmd in ("git stash show -p", "git stash list", "git branch --list", "git tag"):
            self.deny(cmd)

    def test_chunk_path_with_dotdot_after_a_symlink_is_refused(self):
        (self.repo / "graphify-out").mkdir()
        deep = self.repo.parent / "victim" / "deep"
        deep.mkdir(parents=True)
        (self.repo / "lnk").symlink_to(deep)
        self.assertEqual(decide("chunk", "Write", self.repo,
                                file_path="lnk/../graphify-out/.graphify_chunk_01.json"), 2)

    def test_committer_runs_nothing_but_inspection_and_the_commit(self):
        for cmd in ("python3 -B -m pytest -p no:cacheprovider", "make test", "make -n test"):
            self.deny(cmd, "committer")
        other = self.repo.parent / "other"
        other.mkdir()
        self.deny("cd %s && claude-workflow commit --expected-head %s --subject x -- a.py" % (other, HEAD),
                  "committer")
        self.allow("cd %s && git status --short" % self.repo, "committer")


class FifthReview(Guard):
    """Fixes from the final partial independent pass."""

    def test_rg_and_grep_globs_are_limited_to_source_extensions(self):
        for cmd in ("rg -g '*.development' API .", "rg --glob='*.staging' API .", "rg -g '*.{staging,development}' API",
                    "rg --type-add 'x:*.development' -t x API", "rg -g '*.env' API"):
            self.deny(cmd)
        for cmd in ("rg -g '*.py' def", "rg -g '*.{py,md}' x", "rg -g '**/*.py' x", "rg -g 'src/**/*.py' x",
                    "rg -g '*.test.ts' x", "rg -g '!*.min.js' x"):
            self.allow(cmd)
        for pattern in ("*.development", "*.{staging,development}"):
            self.assertEqual(decide("reviewer", "Grep", self.repo, pattern="API", glob=pattern), 2, pattern)
        for pattern in ("*.py", "*.{py,md}", "**/*.ts"):
            self.assertEqual(decide("reviewer", "Grep", self.repo, pattern="API", glob=pattern), 0, pattern)

    def test_rg_pattern_file_value_is_path_checked(self):
        self.deny("rg --file .env x")
        self.deny("rg -f .env x")

    def write_config(self, text, where=".git/config"):
        path = self.repo / where
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_repository_config_variants_that_run_programs(self):
        self.write_config("[core] fsmonitor = /tmp/evil.sh\n")
        self.deny("git status")
        self.write_config("[core]\n\trepositoryformatversion = 1\n[extensions]\n\tworktreeConfig = true\n")
        self.write_config("[core]\n\tfsmonitor = /tmp/evil.sh\n", ".git/config.worktree")
        self.deny("git status")
        self.write_config("[core]\n\trepositoryformatversion = 0\n")
        (self.repo / ".git" / "config.worktree").unlink()
        self.allow("git status --short")

    def test_embedded_bare_repository_config_is_checked(self):
        evil = self.repo / "evil"
        for sub in ("objects", "refs"):
            (evil / sub).mkdir(parents=True)
        (evil / "HEAD").write_text("ref: refs/heads/main\n")
        (evil / "config").write_text("[core]\n\tfsmonitor = /tmp/evil.sh\n")
        (self.repo / ".git").mkdir()
        (self.repo / ".git" / "config").write_text("[core]\n\tbare = false\n")
        self.deny("git -C evil status")
        self.assertEqual(decide("reviewer", "Bash", evil, command="git status"), 2)

    def test_git_grep_attached_pattern_file_is_path_checked(self):
        for cmd in ("git grep -f.env pat", "git grep -nf.env pat", "git grep -f/Users/x/.ssh/id_rsa pat"):
            self.deny(cmd)


class FailClosed(Guard):
    def test_missing_command_and_wrong_shapes_are_denied(self):
        for payload in ({"tool_name": "Bash"}, {"tool_name": "Bash", "tool_input": []},
                        {"tool_name": "Bash", "tool_input": {"command": 7}},
                        {"tool_name": "Read", "tool_input": {}}):
            r = subprocess.run([sys.executable, "-B", str(GUARD), "reviewer"], input=json.dumps(payload),
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, payload)

    def test_internal_errors_block(self):
        r = subprocess.run([sys.executable, "-B", str(GUARD), "reviewer"], input="x" * 10,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
