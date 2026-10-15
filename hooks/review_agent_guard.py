#!/usr/bin/env python3
"""PreToolUse allowlist guard for the read-only review subagents.

Usage (from an agent's frontmatter hook):  python3 -B review_agent_guard.py MODE
  reviewer  Bash may only inspect and run checks; Write/Edit are refused.
  research  For the technical-researcher: Read/Grep/Glob refuse credential paths, and
            WebFetch/WebSearch refuse credentials, non-https URLs, long query strings,
            and long search queries (so repository text cannot be sent out).
  committer For safe-committer: reviewer inspection plus exactly one command,
            `claude-workflow commit --expected-head H --subject S ... -- <paths>`.
  chunk     For graphify-semantic: Read, and Write/Edit of one
            graphify-out/.graphify_chunk_NN.json directly under the working directory.
  security  As reviewer, plus scratch-only mutation: Write/Edit, mkdir, cp, mv,
            touch, chmod, git init/clone/-C, and running scripts, all confined to
            the session scratchpad (/tmp/claude-<uid>/<project>/<session>/scratchpad).

The hook reads the tool call as JSON on stdin. Exit 0 allows it (the normal
permission flow still applies), exit 2 blocks it and returns stderr to the agent.
Anything not recognised is denied, including a parse failure.

Limits: this is an allowlist over a shell command line, not a sandbox. Code the
agent is allowed to run (a repository's tests, or a script it wrote in the
scratchpad) is not confined by this hook.
"""
import fnmatch
import glob as globmod
import ipaddress
import json
import os
import re
import sys

SCRATCH_TEMPLATE = r"^/(?:private/)?tmp/claude-\d+/[^/]+/%s/scratchpad(?:/|$)"


def scratch_re(session=None):
    """The scratchpad pattern; bound to one session when its id is known."""
    if isinstance(session, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", session):
        return re.compile(SCRATCH_TEMPLATE % re.escape(session))
    return re.compile(SCRATCH_TEMPLATE % r"[^/]+")


SCRATCH_RE = scratch_re()
ACTIVE_SCRATCH = SCRATCH_RE
COMMIT_ROOT = None
GLOB_CHARS = set("*?[")
SEPARATORS = (";", "&&", "||", "|")
# A file-descriptor redirect only counts when nothing can continue the target
# name (">&2x" redirects to a file called "2x").
FD_REDIRECT_RE = re.compile(r">&[12](?=\s|$|[;&|])|>\s*/dev/null(?=\s|$|[;&|])")
MAX_EXPANSION = 5000

READ_ONLY = {
    "ls", "cat", "head", "tail", "wc", "pwd", "echo", "printf", "test", "[",
    "basename", "dirname", "realpath", "tr", "cut", "nl", "true", "stat",
    "file", "diff", "grep",
}
FIND_DENIED = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint",
               "-fprint0", "-fprintf", "-fls"}
GIT_READ = {
    "status", "diff", "log", "show", "ls-files", "rev-parse", "rev-list",
    "blame", "grep", "cat-file", "ls-tree", "shortlog", "describe", "diff-tree",
    "diff-index", "merge-base", "name-rev", "for-each-ref", "show-ref",
    "check-ignore",
}
GIT_SCRATCH_DENIED = {"push", "pull", "fetch", "clone", "remote", "send-email",
                      "submodule", "daemon", "credential"}
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SECRET_NAMES = {".netrc", ".npmrc", ".pypirc", ".pgpass", ".git-credentials", "id_rsa", "id_ed25519",
                "id_ecdsa", "id_dsa", "credentials", "credentials.json", "secrets.json",
                ".credentials.json", "hosts.yml", ".bash_history", ".zsh_history", ".seal-key"}
SECRET_DIRS = {".ssh", ".aws", ".gnupg", ".kube", ".docker", "gcloud"}
SECRET_PAIRS = {(".config", "gh"), (".codex", "auth.json"), ("library", "keychains"), (".git", "config")}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".tfstate", ".tfvars", ".kdbx",
                   ".keychain-db")
GLOB_SECRET_HINTS = (".env", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".ssh", ".aws", ".gnupg",
                     ".kube", ".netrc", ".npmrc", ".pypirc", ".pgpass", "credentials", ".pem", ".key",
                     ".p12", ".pfx", "tfstate", "secrets")
MAX_QUERY = 200
SED_SCRIPT_RE = re.compile(r"^(?:\d+|\$)?(?:,(?:\d+|\$))?p$")


class Deny(Exception):
    pass


class Word(str):
    """A shell word; `glob` is True when it holds an unquoted glob character."""
    glob = False


def split_command(command):
    """Split a command line into segments of words; raise Deny on anything risky."""
    if "\n" in command or "\r" in command:
        raise Deny("multi-line commands are not allowed")
    segments, words = [], []
    cur, has_cur, glob = [], False, False
    i, n = 0, len(command)

    def end_word():
        nonlocal cur, has_cur, glob
        if has_cur:
            word = Word("".join(cur))
            word.glob = glob
            words.append(word)
        cur, has_cur, glob = [], False, False

    def end_segment():
        nonlocal words
        end_word()
        if words:
            segments.append(words)
        words = []

    while i < n:
        c = command[i]
        if c == "'":
            j = command.find("'", i + 1)
            if j < 0:
                raise Deny("unterminated quote")
            cur.append(command[i + 1:j])
            has_cur = True
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n and command[j] != '"':
                if command[j] == "\\" and j + 1 < n:
                    if command[j + 1] in '"\\$`':
                        cur.append(command[j + 1])
                    else:
                        cur.append(command[j:j + 2])
                    j += 2
                    continue
                if command[j] == "`":
                    raise Deny("command substitution is not allowed")
                if command[j] == "$" and (j + 1 >= n or re.match(r"[A-Za-z_{(\[0-9?!$@*#-]", command[j + 1])):
                    raise Deny("variable expansion is not allowed")
                cur.append(command[j])
                j += 1
            if j >= n:
                raise Deny("unterminated quote")
            has_cur = True
            i = j + 1
        elif c == "\\":
            if i + 1 >= n:
                raise Deny("trailing backslash")
            cur.append(command[i + 1])
            has_cur = True
            i += 2
        elif c in " \t":
            end_word()
            i += 1
        elif c in "$`":
            raise Deny("variable expansion and command substitution are not allowed")
        elif c in "{}":
            raise Deny("brace expansion and groups are not allowed")
        elif c == "#" and not has_cur:
            raise Deny("comments are not allowed")
        elif c in "()":
            raise Deny("subshells are not allowed")
        elif c == ">":
            m = FD_REDIRECT_RE.match(command, i)
            if m and (not has_cur or "".join(cur) in ("1", "2")):
                cur, has_cur, glob = [], False, False
                i = m.end()
            else:
                raise Deny("redirection is not allowed")
        elif c == "<":
            raise Deny("redirection and heredocs are not allowed")
        elif c == ";":
            end_segment()
            i += 1
        elif c == "|":
            if command.startswith("||", i):
                i += 2
            elif command.startswith("|&", i):
                raise Deny("'|&' is not allowed")
            else:
                i += 1
            end_segment()
        elif c == "&":
            if command.startswith("&&", i):
                end_segment()
                i += 2
            else:
                raise Deny("background execution and '&>' are not allowed")
        else:
            if c in GLOB_CHARS:
                glob = True
            cur.append(c)
            has_cur = True
            i += 1
    end_segment()
    return segments


def resolve(path, cwd):
    return os.path.realpath(os.path.join(cwd, os.path.expanduser(path)))


def in_scratch(word, cwd):
    if getattr(word, "glob", False):
        raise Deny("glob characters are not allowed in a write target: %s" % word)
    return bool(ACTIVE_SCRATCH.match(resolve(word, cwd)))


def need_scratch(words, cwd, what):
    for w in words:
        if not in_scratch(w, cwd):
            raise Deny("%s target %s is outside the session scratchpad" % (what, w))


def flags(args):
    return [a for a in args if a.startswith("-")]


def check_git(args, cwd, mode):
    if args and args[0] == "-C":
        if len(args) < 3:
            raise Deny("git -C needs a path and a subcommand")
        sub = args[2]
        if mode == "security" and in_scratch(args[1], cwd):
            if sub.startswith("-") or sub in GIT_SCRATCH_DENIED:
                raise Deny("git %s is not allowed" % sub)
            if any(a.startswith("--output") for a in args[3:]):
                raise Deny("git --output is not allowed")
            return
        # Any other repository gets the read-only rules only.
        check_secret_path(args[1], cwd)
        return check_git(args[2:], resolve(args[1], cwd), "reviewer")
    if not args or args[0].startswith("-"):
        raise Deny("git global options are not allowed; use a subcommand directly")
    sub, rest = args[0], args[1:]
    if sub not in ("init", "clone"):
        check_repo_config(cwd)
    for a in rest:
        stem = a.split("=", 1)[0]
        if (a.startswith("--output") or a in ("--ext-diff",)
                or (stem.startswith("--ou") and "--output".startswith(stem))):
            raise Deny("git option %s is not allowed" % a)
    if sub in GIT_READ:
        check_repo_config(cwd)
        paths = rest
        if sub == "grep":
            for a in rest:
                stem = a.split("=", 1)[0]
                if re.match(r"^-[A-Za-z0-9]*O", a) or (stem.startswith("--op")
                                                       and "--open-files-in-pager".startswith(stem)):
                    raise Deny("git grep pager execution is not allowed")
                if a.startswith("--") and len(stem) >= 4 and any(
                        long.startswith(stem) for long in ("--no-index", "--untracked", "--no-exclude-standard")):
                    raise Deny("git grep must stay inside tracked files")
            paths = git_grep_paths(rest)
        if sub == "cat-file" and not (rest and rest[0] in ("-t", "-s", "-e")):
            raise Deny("git cat-file may only query an object's type or size")
        after = rest[rest.index("--") + 1:] if "--" in rest else []
        for a in after + [a for a in rest if a.startswith(":")]:
            if lexical_secret_match(a):
                raise Deny("pathspec could match credential files: %s" % a)
        check_read_args(paths, cwd)
        return
    if sub == "branch":
        ok = {"-a", "-r", "-v", "-vv", "--list", "--show-current", "--all", "--remotes"}
        if all(a in ok for a in rest):
            return
    elif sub == "stash":
        if rest and rest[0] in ("list", "show"):
            return
    elif sub == "remote":
        if not rest or rest == ["-v"]:
            return
    elif sub == "config":
        if (len(rest) == 2 and rest[0] in ("--get", "--get-all") and re.fullmatch(r"[A-Za-z0-9.-]+", rest[1])
                and not any(word in rest[1].lower() for word in (
                    "credential", "token", "password", "secret", "pass", "key", "auth"))):
            return
    elif sub == "tag":
        if not rest or rest[0] in ("-l", "--list"):
            return
    elif sub == "worktree":
        if rest == ["list"]:
            return
    elif sub == "init" and mode == "security":
        need_scratch([a for a in rest if not a.startswith("-")] or ["."], cwd, "git init")
        return
    elif sub == "clone" and mode == "security":
        allowed_flags = {"--no-hardlinks", "--local", "-l", "--quiet", "-q", "--bare", "--no-checkout",
                         "-n", "--no-tags", "--single-branch"}
        for a in rest:
            if a.startswith("-") and a not in allowed_flags:
                raise Deny("git clone option %s is not allowed" % a)
        paths = [a for a in rest if not a.startswith("-")]
        if len(paths) != 2 or any(x in paths[0] for x in ("://", "@", ":")):
            raise Deny("git clone is only allowed from a local path")
        need_scratch([paths[1]], cwd, "git clone")
        return
    raise Deny("git %s is not on the allowlist" % sub)


RISKY_CONFIG_KEYS = {"fsmonitor", "external", "textconv", "sshcommand", "pager", "hookspath", "askpass",
                     "clean", "smudge", "process", "command", "program", "editor", "helper", "proxy",
                     "gpgprogram", "cmd"}
HARMLESS_VALUES = {"", "true", "false", "0", "1", "yes", "no", "on", "off"}


def _bare_git_dir(path):
    try:
        return (os.path.isfile(os.path.join(path, "HEAD")) and os.path.isdir(os.path.join(path, "objects"))
                and os.path.isdir(os.path.join(path, "refs")))
    except OSError:
        return False


def _scan_config(text):
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            end = line.find("]")
            section = line[:end + 1].lower() if end > 0 else line.lower()
            if section.startswith("[include"):
                raise Deny("repository config includes other files; refusing to run git")
            line = line[end + 1:].strip() if end > 0 else ""
            if not line:
                continue
        if "=" in line:
            key, value = (part.strip() for part in line.split("=", 1))
            if key.lower() in RISKY_CONFIG_KEYS and value.strip('"').lower() not in HARMLESS_VALUES:
                raise Deny("repository config sets %s, which makes git run a program" % key)


def check_repo_config(cwd):
    """Refuse read-only git in a repository whose own config would run a program."""
    current = os.path.realpath(cwd)
    gitdir = None
    while True:
        marker = os.path.join(current, ".git")
        if os.path.isdir(marker):
            gitdir = marker
            break
        if os.path.isfile(marker):
            try:
                text = open(marker, encoding="utf-8", errors="replace").read()
            except OSError:
                raise Deny("cannot read the gitfile to verify repository config")
            m = re.match(r"gitdir:\s*(.+)", text)
            if not m:
                raise Deny("unrecognised gitfile")
            gitdir = os.path.normpath(os.path.join(current, m.group(1).strip()))
            common = os.path.join(gitdir, "commondir")
            if os.path.isfile(common):
                gitdir = os.path.normpath(os.path.join(gitdir, open(common).read().strip()))
            break
        if _bare_git_dir(current):
            gitdir = current
            break
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent
    for name in ("config", "config.worktree"):
        try:
            text = open(os.path.join(gitdir, name), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        _scan_config(text)


def git_grep_paths(rest):
    """The revision and path arguments of `git grep`, without its search pattern."""
    out, index, after = [], 0, False
    # -e/-f (alone or inside a short-option bundle) mean every positional is a path.
    pattern_given = any(re.match(r"^-[A-Za-z0-9]*[ef]", a) for a in rest if not a.startswith("--") and a != "--")
    while index < len(rest):
        arg = rest[index]
        if after:
            out.append(arg)
        elif arg == "--":
            after = True
        elif arg in ("-e", "-f", "-A", "-B", "-C", "-m", "-j", "--max-depth", "--threads"):
            if arg == "-e":
                pattern_given = True
            elif arg == "-f" and index + 1 < len(rest):
                out.append(rest[index + 1])
            index += 1
        elif re.match(r"^-[A-Za-z0-9]*f.+", arg) and not arg.startswith("--"):
            out.append(re.match(r"^-[A-Za-z0-9]*?f(.+)", arg).group(1))
        elif arg.startswith("-"):
            pass
        elif not pattern_given:
            pattern_given = True
        else:
            out.append(arg)
        index += 1
    return out


def check_commit(args, cwd):
    """The exact shape of `claude-workflow commit` the safe-committer may run."""
    if not args or args[0] != "commit":
        raise Deny("only 'claude-workflow commit' is allowed")
    rest, index, head, subject = args[1:], 0, False, False
    while index < len(rest):
        arg = rest[index]
        if arg == "--":
            break
        if arg in ("--expected-head", "--subject", "--body", "--trailer"):
            if index + 1 >= len(rest) or not rest[index + 1]:
                raise Deny("%s needs a value" % arg)
            if arg == "--expected-head":
                if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", rest[index + 1]):
                    raise Deny("--expected-head must be a full commit hash")
                head = True
            if arg == "--subject":
                subject = True
            index += 2
        elif arg == "--leave-other-staged":
            index += 1
        else:
            raise Deny("claude-workflow commit option %s is not allowed" % arg)
    else:
        raise Deny("claude-workflow commit needs '--' before the exact file paths")
    paths = rest[index + 1:]
    if not (head and subject and paths):
        raise Deny("claude-workflow commit needs --expected-head, --subject and exact paths")
    for path in paths:
        if (path.startswith(("-", ":", "/", "~")) or path in (".", "..") or ".." in path.split("/")
                or any(ch in path for ch in "*?[]{}") or getattr(path, "glob", False)):
            raise Deny("commit path must be an exact relative file path: %s" % path)
        check_secret_path(path, cwd)
        if os.path.isdir(resolve(path, cwd)):
            raise Deny("commit path must be a file, not a directory: %s" % path)


def check_python(args, cwd, mode):
    if args == ["--version"] or args == ["-V"]:
        return
    if not args or args[0] != "-B":
        raise Deny("run python3 with -B so no bytecode is written")
    rest = args[1:]
    if len(rest) >= 2 and rest[0] == "-m" and rest[1] == "unittest":
        return
    if len(rest) >= 2 and rest[0] == "-m" and rest[1] == "pytest":
        if not (any(rest[i] == "-p" and i + 1 < len(rest) and rest[i + 1] == "no:cacheprovider"
                    for i in range(len(rest))) or "-pno:cacheprovider" in rest):
            raise Deny("run pytest with -p no:cacheprovider")
        options = rest[2:]
        denied_prefixes = ("--junit", "--basetemp", "--rootdir", "--confcutdir", "--log-file",
                           "--result", "--cache-dir", "--report-log", "--debug", "--override-ini",
                           "--pastebin", "--doctest", "--pdbcls", "--trace")
        for index, option in enumerate(options):
            if option.startswith(denied_prefixes) or option in ("-o", "-c") or (
                    option.startswith(("-o", "-c")) and len(option) > 2 and not option.startswith("--")):
                raise Deny("pytest option %s writes files or changes configuration" % option)
            if option == "-p" and (index + 1 >= len(options) or options[index + 1] != "no:cacheprovider"):
                raise Deny("only the 'no:cacheprovider' pytest plugin option is allowed")
            if option.startswith("-p") and len(option) > 2 and option != "-pno:cacheprovider":
                raise Deny("only the 'no:cacheprovider' pytest plugin option is allowed")
        return
    if mode == "security" and rest and not rest[0].startswith("-"):
        if in_scratch(rest[0], cwd):
            return
    raise Deny("only 'python3 -B -m unittest|pytest' %s is allowed" %
               ("or a scratchpad script" if mode == "security" else ""))


def check_segment(words, cwd, mode):
    """Validate one command; return the working directory for the next one."""
    cmd, args = words[0], words[1:]
    committer = mode == "committer"
    if committer:
        if cmd == "claude-workflow":
            check_commit(args, cwd)
            return cwd
        if cmd in ("python3", "make"):
            raise Deny("the committer may only inspect and commit")
        mode = "reviewer"
    if cmd == "cd":
        if len(args) != 1 or args[0] == "-" or args[0].startswith("-"):
            raise Deny("cd needs exactly one path")
        if getattr(args[0], "glob", False):
            raise Deny("glob characters are not allowed in a cd target")
        check_secret_path(args[0], cwd)
        target = resolve(args[0], cwd)
        if committer and COMMIT_ROOT and target != COMMIT_ROOT and not target.startswith(COMMIT_ROOT + os.sep):
            raise Deny("the committer may not leave the repository directory")
        return target
    if "/" in cmd:
        if mode == "security" and in_scratch(cmd, cwd) and os.path.isfile(resolve(cmd, cwd)):
            return cwd
        raise Deny("only bare command names are allowed: %s" % cmd)
    if cmd in ("echo", "printf", "true", "pwd", "basename", "dirname", "realpath", "test", "["):
        return cwd
    if cmd in READ_ONLY:
        if cmd == "tail":
            check_tail(args, cwd)
        elif cmd == "grep":
            check_grep(args, cwd)
        elif cmd == "diff":
            check_diff(args, cwd)
        elif cmd == "file":
            check_file(args, cwd)
        else:
            check_read_args(args, cwd)
        return cwd
    if cmd == "rg":
        check_rg(args, cwd)
        return cwd
    if cmd == "find":
        if any(a in FIND_DENIED for a in args):
            raise Deny("find action writes or executes")
        return cwd
    if cmd == "sort":
        check_sort(args, cwd)
        return cwd
    if cmd == "sed":
        if len(args) >= 2 and args[0] == "-n" and SED_SCRIPT_RE.match(args[1]):
            if any(a.startswith("-") for a in args[2:]):
                raise Deny("sed is limited to: sed -n 'N,Mp' file")
            check_read_args(args[2:], cwd)
            return cwd
        raise Deny("sed is limited to: sed -n 'N,Mp' file")
    if cmd == "git":
        check_git(args, cwd, mode)
        return cwd
    if cmd == "python3":
        check_python(args, cwd, mode)
        return cwd
    if cmd == "make":
        for a in args:
            if a.startswith("-") and not (a in ("-n", "--just-print", "--dry-run", "--recon", "-k", "-s",
                                                "--silent", "--quiet", "--keep-going")
                                          or re.fullmatch(r"-j[0-9]*", a)):
                raise Deny("make option %s is not allowed" % a)
        targets = [a for a in args if not a.startswith("-")]
        if any("=" in t for t in targets):
            raise Deny("make variable assignments are not allowed")
        dry = any(a in ("-n", "--just-print", "--dry-run", "--recon") for a in args)
        if not dry and any(t not in ("test", "tests", "check", "lint", "verify") for t in targets):
            raise Deny("make is limited to a dry run (-n) or the test, check, lint and verify targets")
        return cwd
    if mode == "security":
        if cmd == "env":
            rest = list(args)
            while rest and ENV_ASSIGN_RE.match(rest[0]):
                rest.pop(0)
            if not rest or len(rest) == len(args) or rest[0].startswith("-"):
                raise Deny("env is limited to 'env NAME=value... <command>'")
            check_segment(rest, cwd, mode)
            return cwd
        if cmd in ("sh", "bash"):
            if len(args) >= 1 and not args[0].startswith("-") and in_scratch(args[0], cwd):
                return cwd
            raise Deny("only 'sh <scratchpad script>' is allowed")
        if cmd == "mkdir":
            need_scratch([a for a in args if not a.startswith("-")], cwd, "mkdir")
            return cwd
        if cmd == "touch":
            need_scratch([a for a in args if not a.startswith("-")], cwd, "touch")
            return cwd
        if cmd == "chmod":
            mode_re = r"[0-7]{3,4}|[ugoa]*[-+=][rwxXst]+(,[ugoa]*[-+=][rwxXst]+)*"
            if len(args) < 2 or not re.fullmatch(mode_re, args[0]):
                raise Deny("chmod needs a plain mode followed by scratchpad paths")
            if any(a.startswith("-") for a in args[1:]):
                raise Deny("chmod options are not allowed")
            need_scratch(args[1:], cwd, "chmod")
            return cwd
        if cmd == "cp":
            paths = positional_after_options(
                args, {"--recursive", "--preserve", "--force", "--no-clobber", "--verbose", "--archive"},
                set("rRpfnvai"), what="cp option")
            if len(paths) < 2:
                raise Deny("cp needs a source and a destination")
            check_read_args(paths[:-1], cwd)
            need_scratch([paths[-1]], cwd, "cp")
            return cwd
        if cmd == "mv":
            paths = positional_after_options(
                args, {"--force", "--no-clobber", "--verbose"}, set("fnvi"), what="mv option")
            if len(paths) < 2:
                raise Deny("mv needs a source and a destination")
            need_scratch(paths, cwd, "mv")
            return cwd
    raise Deny("%s is not on the allowlist" % cmd)


SORT_LONG = {"--unique", "--numeric-sort", "--reverse", "--ignore-case", "--ignore-leading-blanks",
             "--dictionary-order", "--general-numeric-sort", "--human-numeric-sort", "--month-sort",
             "--version-sort", "--stable", "--zero-terminated", "--ignore-nonprinting",
             "--ignore-case"}
SORT_SHORT = set("bdfghiMnRrsuVz")
GREP_LONG = {"--ignore-case", "--line-number", "--invert-match", "--word-regexp", "--line-regexp",
             "--count", "--files-with-matches", "--files-without-match", "--extended-regexp",
             "--fixed-strings", "--basic-regexp", "--no-messages", "--quiet", "--silent",
             "--only-matching", "--with-filename", "--no-filename", "--text"}
GREP_SHORT = set("nivwxclLEFGHhqsaoIz")
DIFF_LONG = {"--unified", "--brief", "--ignore-case", "--ignore-all-space", "--ignore-space-change",
             "--ignore-blank-lines", "--ignore-trailing-space", "--strip-trailing-cr", "--text",
             "--side-by-side", "--expand-tabs", "--normal", "--context"}
DIFF_SHORT = set("uqiwbBEZaycs")
FILE_LONG = {"--brief", "--mime", "--mime-type", "--mime-encoding", "--dereference", "--no-dereference"}
FILE_SHORT = set("biLhnNsEkp")
TAIL_LONG = {"--quiet", "--silent", "--verbose"}


def positional_after_options(args, long_ok, short_ok, valued=(), what="option"):
    """Return positional arguments, refusing every option not on the exact allowlist."""
    positional, index = [], 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positional.extend(args[index + 1:])
            break
        if arg.startswith("--"):
            if arg not in long_ok:
                raise Deny("%s %s is not on the allowlist" % (what, arg))
        elif arg.startswith("-") and len(arg) > 1:
            if arg in valued:
                index += 1
                if index >= len(args):
                    raise Deny("%s %s needs a value" % (what, arg))
            elif re.fullmatch(r"-[0-9]+", arg) or re.fullmatch(r"-[%s][0-9]+" % "".join(
                    v[1] for v in valued if len(v) == 2 and v[1].isalpha()) or "!", arg):
                pass
            elif not all(ch in short_ok for ch in arg[1:]):
                raise Deny("%s %s is not on the allowlist" % (what, arg))
        else:
            positional.append(arg)
        index += 1
    return positional


def check_sort(args, cwd):
    files, index = [], 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            files.extend(args[index + 1:])
            break
        if arg.startswith("--"):
            if arg not in SORT_LONG:
                raise Deny("sort option %s is not allowed" % arg)
        elif arg in ("-k", "-t"):
            index += 1
            if index >= len(args) or not re.fullmatch(r"[0-9.,bdfgiMhnRrV]{1,16}|.", args[index]):
                raise Deny("sort %s needs a plain value" % arg)
        elif re.fullmatch(r"-[bdfghiMnRrsuVz]*k[0-9.,bdfgiMhnRrV]+|-t.", arg):
            pass
        elif arg.startswith("-") and len(arg) > 1:
            if not all(ch in SORT_SHORT for ch in arg[1:]):
                raise Deny("sort option %s is not allowed" % arg)
        else:
            files.append(arg)
        index += 1
    check_read_args(files, cwd)


def check_grep(args, cwd):
    positional, index, via_option = [], 0, False
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positional.extend(args[index + 1:])
            break
        if arg.startswith("--"):
            if not (arg in GREP_LONG or re.fullmatch(
                    r"--(regexp|max-count|after-context|before-context|context)=.+", arg)):
                raise Deny("grep option %s is not allowed (no recursion, no pattern files)" % arg)
            if arg.startswith("--regexp="):
                via_option = True
        elif arg in ("-e", "-m", "-A", "-B", "-C"):
            if arg == "-e":
                via_option = True
            index += 1
            if index >= len(args):
                raise Deny("grep %s needs a value" % arg)
        elif re.fullmatch(r"-[ABCm][0-9]+|-[0-9]+|-e.+", arg):
            via_option = via_option or arg.startswith("-e")
        elif arg.startswith("-") and len(arg) > 1:
            if not all(ch in GREP_SHORT for ch in arg[1:]):
                raise Deny("grep option %s is not allowed (no recursion, no pattern files)" % arg)
        else:
            positional.append(arg)
        index += 1
    if not via_option and positional:
        positional = positional[1:]  # the search pattern is not a path
    check_read_args(positional, cwd)


def check_diff(args, cwd):
    positional, after = [], False
    for arg in args:
        if after:
            positional.append(arg)
        elif arg == "--":
            after = True
        elif arg.startswith("--"):
            if arg not in DIFF_LONG and not re.fullmatch(r"--unified=[0-9]+|--context=[0-9]+", arg):
                raise Deny("diff option %s is not allowed (no recursion)" % arg)
        elif arg.startswith("-") and len(arg) > 1:
            if not (re.fullmatch(r"-[UC][0-9]+", arg) or all(ch in DIFF_SHORT for ch in arg[1:])):
                raise Deny("diff option %s is not allowed (no recursion)" % arg)
        else:
            positional.append(arg)
    for path in positional:
        if os.path.isdir(resolve(path, cwd)):
            raise Deny("diff of directories is not allowed")
    check_read_args(positional, cwd)


def check_file(args, cwd):
    positional = []
    for arg in args:
        if arg.startswith("--"):
            if arg not in FILE_LONG:
                raise Deny("file option %s is not allowed" % arg)
        elif arg.startswith("-") and len(arg) > 1:
            if not all(ch in FILE_SHORT for ch in arg[1:]):
                raise Deny("file option %s is not allowed" % arg)
        else:
            positional.append(arg)
    check_read_args(positional, cwd)


def check_tail(args, cwd):
    positional, index = [], 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positional.extend(args[index + 1:])
            break
        if arg.startswith("--"):
            if not (arg in TAIL_LONG or re.fullmatch(r"--(lines|bytes)=[+-]?[0-9]+", arg)):
                raise Deny("tail option %s is not allowed" % arg)
        elif arg in ("-n", "-c"):
            index += 1
            if index >= len(args) or not re.fullmatch(r"[+-]?[0-9]+", args[index]):
                raise Deny("tail %s needs a number" % arg)
        elif re.fullmatch(r"-[nc][+-]?[0-9]+|-[0-9]+", arg):
            pass
        elif arg.startswith("-") and len(arg) > 1:
            if not all(ch in "qv" for ch in arg[1:]):
                raise Deny("tail option %s is not allowed" % arg)
        else:
            positional.append(arg)
        index += 1
    check_read_args(positional, cwd)


POSIX_CLASS_RE = re.compile(r"\[\[:[a-z]+:\]\]|\[:[a-z]+:\]")
PATTERN_OPTIONS = ("--grep=", "--author=", "--committer=", "--regexp=", "--pretty=", "--format=")


def lexical_secret_match(pattern):
    """True when a glob's final component could name a credential file."""
    final = POSIX_CLASS_RE.sub("?", pattern.replace("\\", "/")).replace("[^", "[!")
    final = final.rstrip("/").split("/")[-1].lower()
    if not any(c in final for c in GLOB_CHARS):
        return False
    samples = set(SECRET_NAMES) | {".env", ".env.local", ".env.production", ".envrc", "prod.env"}
    samples |= {"x" + suffix for suffix in SECRET_SUFFIXES}
    return any(fnmatch.fnmatch(sample, final) for sample in samples)


def check_secret_path(path, cwd):
    if not path:
        return
    resolved = resolve(path, cwd)
    parts = [part.lower() for part in resolved.split(os.sep)]
    name = parts[-1]
    pairs = set(zip(parts, parts[1:]))
    if (name.startswith(".env") or name.endswith(".env") or ".env." in name
            or name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES)
            or any(part in SECRET_DIRS for part in parts)
            or pairs & SECRET_PAIRS or resolved.startswith("/proc/")):
        raise Deny("credential paths are off limits: %s" % path)


def check_read_args(args, cwd):
    """Refuse a read-only command whose arguments name a credential file or directory.

    An argument counts as a path when it exists, contains a slash, starts with a dot, or
    follows a colon (`HEAD:.env`), so a search pattern such as `credentials` is not mistaken
    for one.
    """
    for arg in args:
        if getattr(arg, "glob", False):
            raise Deny("unquoted glob characters are not allowed; quote a pattern or name the file: %s" % arg)
        if arg.startswith(PATTERN_OPTIONS) or re.match(r"^-[SG].+", arg):
            continue
        candidates = [(arg, False)]
        for sep in ("=", ":"):
            if sep in arg:
                candidates.append((arg.split(sep, 1)[1], sep == ":"))
        for cand, from_colon in candidates:
            if not cand or cand.startswith("-"):
                continue
            if (from_colon or "/" in cand or cand.startswith(".") or cand.startswith("~")
                    or cand.lower().endswith(SECRET_SUFFIXES + (".env",))
                    or os.path.lexists(resolve(cand, cwd))):
                check_secret_path(cand, cwd)


RG_VALUED = {"-g", "--glob", "--iglob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C", "-m",
             "--max-count", "-e", "--regexp", "-j", "--threads", "-M", "--max-columns", "-d", "--max-depth",
             "-E", "--encoding", "-f", "--file"}


SOURCE_EXTENSIONS = {
    "py", "pyi", "js", "jsx", "mjs", "cjs", "ts", "tsx", "md", "mdx", "rst", "txt", "json", "yaml", "yml",
    "toml", "rs", "go", "java", "kt", "c", "h", "cc", "cpp", "hpp", "cs", "rb", "php", "sh", "bash", "zsh",
    "html", "css", "scss", "sql", "v", "sv", "svh", "vhd", "vhdl", "tcl", "xdc", "sdc", "lua", "swift",
    "scala", "ex", "exs", "pl", "r", "ipynb", "cfg", "ini", "xml", "svg", "csv", "tex", "bib", "cmake", "mk",
}
POSITIVE_GLOB_RE = re.compile(r"(?:(?:\*\*|[A-Za-z0-9_-]+)/)*\*(?:\.[A-Za-z0-9_-]+)*\.([A-Za-z0-9]+)")


def check_positive_glob(value):
    """A positive glob overrides hidden-file and ignore rules: allow only source-extension globs."""
    if value.startswith("!"):
        return
    for alternative in brace_expand(value):
        match = POSITIVE_GLOB_RE.fullmatch(alternative)
        if (not match or match.group(1).lower() not in SOURCE_EXTENSIONS
                or lexical_secret_match(alternative)):
            raise Deny("glob %s could override hidden-file rules or name credentials" % value)


def check_rg(args, cwd):
    if any(a.startswith(("--pre", "--hostname-bin")) for a in args):
        raise Deny("rg option runs a program")

    def glob_hint(value):
        check_positive_glob(value)

    paths, pattern_given, index, after = [], False, 0, False
    while index < len(args):
        arg = args[index]
        if after:
            paths.append(arg)
        elif arg == "--":
            after = True
        elif arg in ("--hidden", "--unrestricted") or arg.startswith("--no-ignore"):
            raise Deny("rg must respect hidden files and ignore rules")
        elif arg.startswith("--"):
            stem, _, value = arg.partition("=")
            if stem in ("--glob", "--iglob") and value:
                glob_hint(value)
            if stem in ("--regexp", "--file", "--files", "--type-list"):
                pattern_given = True
                if stem == "--file" and value:
                    paths.append(value)
            if stem in ("--type-add", "--type-clear"):
                raise Deny("rg type definitions are not allowed")
            if "=" not in arg and stem in RG_VALUED:
                index += 1
                if stem in ("--glob", "--iglob") and index < len(args):
                    glob_hint(args[index])
                if stem == "--file" and index < len(args):
                    paths.append(args[index])
        elif arg.startswith("-") and len(arg) > 1:
            for pos in range(1, len(arg)):
                letter = arg[pos]
                if letter in "u.":
                    raise Deny("rg must respect hidden files and ignore rules")
                if "-" + letter in RG_VALUED:
                    value = arg[pos + 1:]
                    if not value:
                        index += 1
                        value = args[index] if index < len(args) else ""
                    if letter == "g":
                        glob_hint(value)
                    if letter in "ef":
                        pattern_given = True
                    if letter == "f":
                        paths.append(value)
                    break
        elif not pattern_given:
            pattern_given = True
        else:
            paths.append(arg)
        index += 1
    check_read_args(paths, cwd)


def check_url(url):
    from urllib.parse import urlsplit
    parts = urlsplit(url or "")
    if parts.scheme != "https" or not parts.hostname:
        raise Deny("only https URLs are allowed")
    if parts.username or parts.password:
        raise Deny("URLs with embedded credentials are not allowed")
    if len(parts.query) > MAX_QUERY or len(parts.fragment) > MAX_QUERY:
        raise Deny("URL query or fragment is too long to be a documentation lookup")
    if len(url) > 500:
        raise Deny("URL is too long")
    host = (parts.hostname or "").lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
        raise Deny("IP-literal hosts are not allowed")
    except ValueError:
        pass
    if re.fullmatch(r"(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+))*", host):
        raise Deny("numeric hosts are not allowed")
    if "." not in host or host == "localhost" or host.endswith((
            ".local", ".localhost", ".internal", ".lan", ".home", ".home.arpa", ".corp", ".intranet", ".test",
            ".invalid", ".example", ".private", ".lan", ".localdomain", ".svc", ".cluster.local")):
        raise Deny("only public documentation hosts are allowed")
    if any(len(label) > 40 for label in host.split(".")):
        raise Deny("host name is too long to be a documentation site")
    if len(parts.path) > 300:
        raise Deny("URL path is too long to be a documentation lookup")


def check_bash(command, cwd, mode):
    for words in split_command(command):
        cwd = check_segment(words, cwd, mode)


def brace_expand(pattern, limit=64):
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    out = []
    for alternative in match.group(1).split(","):
        out.extend(brace_expand(pattern[:match.start()] + alternative + pattern[match.end():], limit))
        if len(out) > limit:
            raise Deny("glob expands to too many alternatives to verify")
    return out


def check_wildcard_pattern(pattern, cwd):
    """Refuse a Glob/Grep pattern that could select credential files or directories."""
    for alternative in brace_expand(pattern):
        if "(" in alternative or ")" in alternative:
            raise Deny("extended glob syntax cannot be verified: %s" % pattern)
        alternative = POSIX_CLASS_RE.sub("?", alternative.replace("\\", "/")).replace("[^", "[!")
        components = [c for c in alternative.split("/") if c not in ("", ".")]
        previous = None
        for index, component in enumerate(components):
            final = index == len(components) - 1
            low = component.lower()
            if not any(ch in component for ch in GLOB_CHARS):
                check_secret_path(component, cwd)
                if previous is not None and (previous.lower(), low) in SECRET_PAIRS:
                    raise Deny("glob names a credential file: %s" % pattern)
                previous = component
                continue
            previous = None
            if component.strip("*?") and not final and any(fnmatch.fnmatch(d, low) for d in SECRET_DIRS):
                raise Deny("glob could descend into a credential directory: %s" % pattern)
            if final and lexical_secret_match(component):
                raise Deny("glob could match credential files: %s" % pattern)


def check_read_tool(tool, tool_input, cwd):
    """Read, Grep, and Glob refuse credential paths and credential-shaped globs."""
    required = {"Read": "file_path", "Glob": "pattern", "Grep": "pattern"}[tool]
    if not isinstance(tool_input.get(required), str) or not tool_input[required]:
        raise Deny("a %s call needs a non-empty %s" % (tool, required))
    home = os.path.realpath(os.path.expanduser("~"))
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if value is not None and not isinstance(value, str):
            raise Deny("%s must be a string" % key)
        check_secret_path(value or "", cwd)
        if tool in ("Grep", "Glob") and key == "path" and resolve(value or ".", cwd) in (home, "/"):
            raise Deny("searching the home directory or filesystem root could reach credentials")
    patterns = []
    if tool == "Glob":
        patterns.append(tool_input.get("pattern"))
    if tool == "Grep":
        patterns.append(tool_input.get("glob"))
    for pattern in patterns:
        if pattern is None:
            continue
        if not isinstance(pattern, str):
            raise Deny("glob must be a string")
        check_wildcard_pattern(pattern, cwd)
        if tool == "Grep":
            check_positive_glob(pattern)
    if tool == "Grep":
        for key in ("type",):
            if tool_input.get(key) is not None and not isinstance(tool_input.get(key), str):
                raise Deny("%s must be a string" % key)


def check_chunk_path(path, cwd):
    if not isinstance(path, str) or not path:
        raise Deny("a chunk write needs a file path")
    if ".." in path.replace("\\", "/").split("/"):
        raise Deny("chunk paths must not contain '..'")
    absolute = os.path.abspath(os.path.join(cwd, path))
    parent = os.path.dirname(absolute)
    if (not re.fullmatch(r"\.graphify_chunk_[0-9]{1,4}\.json", os.path.basename(absolute))
            or os.path.basename(parent) != "graphify-out"):
        raise Deny("writes are limited to graphify-out/.graphify_chunk_NN.json: %s" % path)
    if os.path.islink(parent) or os.path.islink(absolute):
        raise Deny("the chunk path must not be a symlink: %s" % path)
    if os.path.realpath(parent) != os.path.join(os.path.realpath(cwd), "graphify-out"):
        raise Deny("the chunk must be under the working directory's graphify-out: %s" % path)


def decide(data, mode):
    global ACTIVE_SCRATCH
    if not isinstance(data, dict):
        raise Deny("tool call must be a JSON object")
    tool = data.get("tool_name")
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        raise Deny("tool_input must be an object")
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and data.get("cwd") else os.getcwd()
    global COMMIT_ROOT
    COMMIT_ROOT = os.path.realpath(cwd)
    session = data.get("session_id")
    valid = isinstance(session, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", session)
    ACTIVE_SCRATCH = scratch_re(session) if valid else re.compile(r"(?!)")
    if mode == "chunk":
        if tool == "Read":
            check_read_tool(tool, tool_input, cwd)
        elif tool in ("Write", "Edit"):
            check_chunk_path(tool_input.get("file_path"), cwd)
        else:
            raise Deny("unexpected tool %s" % tool)
        return
    if tool in ("Read", "Grep", "Glob"):
        check_read_tool(tool, tool_input, cwd)
        return
    if mode == "research":
        if tool == "WebFetch":
            check_url(tool_input.get("url"))
        elif tool == "WebSearch":
            query = tool_input.get("query") or ""
            if not isinstance(query, str):
                raise Deny("search query must be a string")
            if len(query) > MAX_QUERY:
                raise Deny("search query is too long; use a short, generic query")
        else:
            raise Deny("unexpected tool %s" % tool)
        return
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            raise Deny("a Bash call needs a non-empty command string")
        check_bash(command, cwd, mode)
    elif tool in ("Write", "Edit", "NotebookEdit"):
        if mode != "security":
            raise Deny("this agent is read-only; report the change as a recommendation")
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if not path or not in_scratch(path, cwd):
            raise Deny("writes are limited to the session scratchpad: %s" % path)
    else:
        raise Deny("unexpected tool %s" % tool)


def main(argv):
    mode = argv[1] if len(argv) > 1 else ""
    try:
        if mode not in ("reviewer", "security", "research", "committer", "chunk"):
            raise Deny("guard mode must be 'reviewer', 'security', 'research', 'committer' or 'chunk'")
        decide(json.load(sys.stdin), mode)
    except Deny as exc:
        print("Blocked by review_agent_guard (%s): %s. Report it as a recommendation "
              "or, for an experiment, use the security-reviewer agent." % (mode, exc),
              file=sys.stderr)
        return 2
    except BaseException as exc:  # fail closed on any malformed input or internal error
        print("Blocked by review_agent_guard: could not evaluate the call (%s)" % exc,
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
