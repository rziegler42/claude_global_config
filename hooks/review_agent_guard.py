#!/usr/bin/env python3
"""PreToolUse allowlist guard for the read-only review subagents.

Usage (from an agent's frontmatter hook):  python3 -B review_agent_guard.py MODE
  reviewer  Bash may only inspect and run checks; Write/Edit are refused.
  research  For the technical-researcher: Read/Grep/Glob refuse credential paths, and
            WebFetch/WebSearch refuse credentials, non-https URLs, long query strings,
            and long search queries (so repository text cannot be sent out).
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
import json
import os
import re
import sys

SCRATCH_RE = re.compile(r"^/(?:private/)?tmp/claude-\d+/[^/]+/[^/]+/scratchpad(?:/|$)")
GLOB_CHARS = set("*?[")
SEPARATORS = (";", "&&", "||", "|")
FD_REDIRECT_RE = re.compile(r">&[12]|>\s*/dev/null")

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
                "id_ecdsa", "id_dsa", "credentials", "credentials.json", "secrets.json"}
SECRET_DIRS = {".ssh", ".aws", ".gnupg", ".kube", ".docker", "gcloud"}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".tfstate")
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
    if "`" in command or "$(" in command:
        raise Deny("command substitution is not allowed")
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
                if command[j] == "$":
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
        elif c == "$":
            raise Deny("variable expansion is not allowed")
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
    return bool(SCRATCH_RE.match(resolve(word, cwd)))


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
        return check_git(args[2:], cwd, "reviewer")
    if not args or args[0].startswith("-"):
        raise Deny("git global options are not allowed; use a subcommand directly")
    sub, rest = args[0], args[1:]
    for a in rest:
        if a.startswith("--output") or a in ("--ext-diff",):
            raise Deny("git option %s is not allowed" % a)
    if sub in GIT_READ:
        if sub == "grep" and any(a == "-O" or a.startswith("--open-files-in-pager") for a in rest):
            raise Deny("git grep pager execution is not allowed")
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
        if rest and rest[0] in ("--get", "--get-all", "--list", "-l"):
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
        paths = [a for a in rest if not a.startswith("-")]
        if len(paths) != 2 or any(x in paths[0] for x in ("://", "@", ":")):
            raise Deny("git clone is only allowed from a local path")
        need_scratch([paths[1]], cwd, "git clone")
        return
    raise Deny("git %s is not on the allowlist" % sub)


def check_python(args, cwd, mode):
    if args == ["--version"] or args == ["-V"]:
        return
    if not args or args[0] != "-B":
        raise Deny("run python3 with -B so no bytecode is written")
    rest = args[1:]
    if len(rest) >= 2 and rest[0] == "-m" and rest[1] == "unittest":
        return
    if len(rest) >= 2 and rest[0] == "-m" and rest[1] == "pytest":
        if "no:cacheprovider" not in rest:
            raise Deny("run pytest with -p no:cacheprovider")
        return
    if mode == "security" and rest and not rest[0].startswith("-"):
        if in_scratch(rest[0], cwd):
            return
    raise Deny("only 'python3 -B -m unittest|pytest' %s is allowed" %
               ("or a scratchpad script" if mode == "security" else ""))


def check_segment(words, cwd, mode):
    """Validate one command; return the working directory for the next one."""
    cmd, args = words[0], words[1:]
    if cmd == "cd":
        if len(args) != 1 or args[0] == "-" or args[0].startswith("-"):
            raise Deny("cd needs exactly one path")
        return resolve(args[0], cwd)
    if "/" in cmd:
        if mode == "security" and in_scratch(cmd, cwd) and os.path.isfile(resolve(cmd, cwd)):
            return cwd
        raise Deny("only bare command names are allowed: %s" % cmd)
    if cmd in READ_ONLY:
        if cmd == "tail" and any(a in ("-f", "-F", "--follow") for a in args):
            raise Deny("tail -f never returns")
        return cwd
    if cmd == "rg":
        if any(a.startswith(("--pre", "--hostname-bin")) for a in args):
            raise Deny("rg option runs a program")
        return cwd
    if cmd == "find":
        if any(a in FIND_DENIED for a in args):
            raise Deny("find action writes or executes")
        return cwd
    if cmd == "sort":
        for a in args:
            if (a.startswith("--output") or a.startswith("--compress-program")
                    or re.match(r"^-[A-Za-z]*o", a)):
                raise Deny("sort option writes or executes")
        return cwd
    if cmd == "sed":
        if len(args) >= 2 and args[0] == "-n" and SED_SCRIPT_RE.match(args[1]):
            return cwd
        raise Deny("sed is limited to: sed -n 'N,Mp' file")
    if cmd == "git":
        check_git(args, cwd, mode)
        return cwd
    if cmd == "python3":
        check_python(args, cwd, mode)
        return cwd
    if cmd == "make":
        if any(a.startswith(("-f", "-C", "-I", "--file", "--makefile", "--directory",
                             "--include-dir")) for a in args):
            raise Deny("make -f/-C/-I are not allowed")
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
            paths = [a for a in args if not a.startswith("-")][1:]
            if not paths:
                raise Deny("chmod needs a mode and a path")
            need_scratch(paths, cwd, "chmod")
            return cwd
        if cmd == "cp":
            if any(a.startswith(("-t", "--target-directory")) for a in args):
                raise Deny("cp -t is not allowed")
            paths = [a for a in args if not a.startswith("-")]
            if len(paths) < 2:
                raise Deny("cp needs a source and a destination")
            need_scratch([paths[-1]], cwd, "cp")
            return cwd
        if cmd == "mv":
            paths = [a for a in args if not a.startswith("-")]
            if len(paths) < 2 or any(a.startswith(("-t", "--target-directory")) for a in args):
                raise Deny("mv needs source and destination, without -t")
            need_scratch(paths, cwd, "mv")
            return cwd
    raise Deny("%s is not on the allowlist" % cmd)


def check_secret_path(path, cwd):
    if not path:
        return
    resolved = resolve(path, cwd)
    parts = resolved.split(os.sep)
    name = parts[-1].lower()
    if (name.startswith(".env") or name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES)
            or any(part in SECRET_DIRS for part in parts[:-1] + [parts[-1]])):
        raise Deny("credential paths are off limits: %s" % path)


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


def check_bash(command, cwd, mode):
    for words in split_command(command):
        cwd = check_segment(words, cwd, mode)


def decide(data, mode):
    tool = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if mode == "research":
        if tool in ("Read", "Grep", "Glob"):
            for key in ("file_path", "path", "pattern" if tool == "Glob" else "path"):
                check_secret_path(tool_input.get(key) or "", cwd)
        elif tool == "WebFetch":
            check_url(tool_input.get("url"))
        elif tool == "WebSearch":
            if len(tool_input.get("query") or "") > MAX_QUERY:
                raise Deny("search query is too long; use a short, generic query")
        else:
            raise Deny("unexpected tool %s" % tool)
        return
    if tool == "Bash":
        check_bash(tool_input.get("command") or "", cwd, mode)
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
        if mode not in ("reviewer", "security", "research"):
            raise Deny("guard mode must be 'reviewer', 'security' or 'research'")
        decide(json.load(sys.stdin), mode)
    except Deny as exc:
        print("Blocked by review_agent_guard (%s): %s. Report it as a recommendation "
              "or, for an experiment, use the security-reviewer agent." % (mode, exc),
              file=sys.stderr)
        return 2
    except Exception as exc:  # fail closed on any malformed input
        print("Blocked by review_agent_guard: could not evaluate the call (%s)" % exc,
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
