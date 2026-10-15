#!/usr/bin/env python3
"""Install the tracked Claude configuration into ~/.claude.

Usage: ./install.py [--dry-run | --check] [--no-link-bin]

Installs the files listed in config-manifest.txt into
${CLAUDE_CONFIG_DIR:-$HOME/.claude}. Changed destination files are backed up
before replacement. Nothing is ever deleted. Standard library only.

settings.json is handled by policy (settings-policy.txt) instead of a byte
comparison, and file modes are checked (they are only ever tightened, or the
owner execute bit restored); see README.md.
"""
import json
import os
import posixpath
import shutil
import stat
import sys
import tempfile
import time

HELPERS = ("claude-workflow", "remote-runner")
SETTINGS = "settings.json"
POLICY_FILE = "settings-policy.txt"
PLUGIN_REGISTRY = os.path.join("plugins", "installed_plugins.json")
KINDS = ("preference", "open")
# A mistake guard: these settings change what runs or is permitted, so a policy
# file may not relax them to "preference" or "open". Unlisted keys are still
# strict by default; this only blocks an accidental or malicious relaxation.
PROTECTED = (
    "/permissions",
    "/hooks",
    "/env",
    "/apiKeyHelper",
    "/statusLine",
    "/fileSuggestion",
    "/mcpServers",
    "/enableAllProjectMcpServers",
    "/enabledMcpjsonServers",
    "/disabledMcpjsonServers",
    "/allowedMcpServers",
    "/extraKnownMarketplaces",
    "/awsAuthRefresh",
    "/awsCredentialExport",
    "/gcpAuthRefresh",
    "/otelHeadersHelper",
    "/sandbox",
    "/disableAllHooks",
    "/skipDangerousModePermissionPrompt",
)
USAGE = (
    "Usage: ./install.py [--dry-run | --check] [--no-link-bin]\n"
    "\n"
    "Installs the tracked files into ${CLAUDE_CONFIG_DIR:-$HOME/.claude}.\n"
    "Changed destination files are backed up before replacement.\n"
)


class ConfigError(Exception):
    """A problem with the inputs or environment; reported on stderr, exit 2."""


def safe_text(text):
    """Escape control characters so file data cannot drive the terminal."""
    return "".join(
        ch if ch == "\n" or (ch.isprintable() and ch != "\x7f") else "\\x%02x" % ord(ch)
        for ch in text
    )


class SafeStream:
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        self.stream.write(safe_text(text))


def read_text(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError("Cannot read %s: %s" % (label, exc.__class__.__name__))


# --------------------------------------------------------------------------
# Manifest and sources


def read_manifest(repo_dir):
    entries = []
    seen = set()
    lines = read_text(os.path.join(repo_dir, "config-manifest.txt"), "manifest").splitlines()
    for rel in lines:
        if not rel or rel.startswith("#"):
            continue
        if (
            rel.startswith("/")
            or ".." in rel.split("/")
            or "\0" in rel
            or posixpath.normpath(rel) != rel
        ):
            raise ConfigError("Unsafe manifest path: %s" % rel)
        folded = rel.casefold()
        if folded == SETTINGS.casefold() and rel != SETTINGS:
            raise ConfigError(
                "Unsafe manifest path: %s (case variant of %s, which is policy-managed)"
                % (rel, SETTINGS)
            )
        if folded in seen:
            raise ConfigError("Duplicate manifest path: %s" % rel)
        seen.add(folded)
        entries.append(rel)
    return entries


def check_source(repo_dir, path):
    """Sources must be regular files that resolve inside the repository."""
    if os.path.islink(path):
        raise ConfigError("Refusing symlinked source: %s" % path)
    if not os.path.isfile(path):
        raise ConfigError("Missing source file: %s" % path)
    root = os.path.realpath(repo_dir)
    real = os.path.realpath(path)
    if real != root and not real.startswith(root + os.sep):
        raise ConfigError("Source resolves outside the repository: %s" % path)


def inside(path, root):
    return path == root or path.startswith(root + os.sep)


def check_destinations(entries, target_dir):
    """Destinations must stay in the config dir and never alias settings.json."""
    root = os.path.realpath(target_dir)
    settings_real = os.path.realpath(os.path.join(target_dir, SETTINGS))
    for rel in entries:
        destination = os.path.join(target_dir, rel)
        if not inside(os.path.realpath(os.path.dirname(destination)), root):
            raise ConfigError("Destination escapes the configuration directory: %s" % rel)
        if rel != SETTINGS and os.path.realpath(destination) == settings_real:
            raise ConfigError(
                "Destination %s aliases %s, which is policy-managed" % (rel, SETTINGS)
            )


def same_file(source, destination):
    if not os.path.isfile(destination):
        return False
    with open(source, "rb") as a, open(destination, "rb") as b:
        return a.read() == b.read()


# --------------------------------------------------------------------------
# settings.json policy


def load_policy(repo_dir):
    """Return {pointer: kind}; anything not listed is strict."""
    path = os.path.join(repo_dir, POLICY_FILE)
    policy = {}
    if not os.path.lexists(path):
        return policy
    check_source(repo_dir, path)
    for number, raw in enumerate(read_text(path, POLICY_FILE).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        where = "%s:%d" % (POLICY_FILE, number)
        parts = line.split()
        if len(parts) != 2 or parts[0] not in KINDS:
            raise ConfigError("%s: expected 'preference <path>' or 'open <path>'" % where)
        pointer = parts[1]
        segments = pointer.split("/")
        if not pointer.startswith("/") or len(segments) < 2 or "" in segments[1:] or ".." in segments:
            raise ConfigError("%s: invalid path %r" % (where, pointer))
        for guarded in PROTECTED:
            if pointer == guarded or pointer.startswith(guarded + "/"):
                raise ConfigError(
                    "%s: %s is a protected setting and cannot be a %s" % (where, pointer, parts[0])
                )
        if pointer in policy:
            raise ConfigError("%s: duplicate policy path %s" % (where, pointer))
        policy[pointer] = parts[0]
    return policy


def escape(key):
    return key.replace("~", "~0").replace("/", "~1")


def same_json(a, b):
    """Type-aware equality: False != 0, True != 1, 1 != 1.0 (as JSON text)."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def merge(repo, local, pointer, policy):
    """Return the settings the installed file should have.

    strict (default): repo value wins; local-only keys are dropped.
    preference: local value kept when present, repo value seeds when absent.
    open (dict): repo entries enforced, local-only entries kept.
    """
    out = {}
    local_is_dict = isinstance(local, dict)
    for key, repo_value in repo.items():
        child = pointer + "/" + escape(key)
        kind = policy.get(child)
        has_local = local_is_dict and key in local
        local_value = local[key] if has_local else None
        if kind == "preference":
            out[key] = local_value if has_local else repo_value
        elif kind == "open" and isinstance(repo_value, dict) and isinstance(local_value, dict):
            merged = dict(local_value)
            merged.update(repo_value)
            out[key] = merged
        elif isinstance(repo_value, dict) and isinstance(local_value, dict):
            out[key] = merge(repo_value, local_value, child, policy)
        else:
            out[key] = repo_value
    if local_is_dict:
        for key, local_value in local.items():
            if key not in repo and policy.get(pointer + "/" + escape(key)) in KINDS:
                out[key] = local_value
    return out


def describe(desired, local, pointer, lines):
    if isinstance(desired, dict) and isinstance(local, dict):
        for key in desired:
            child = pointer + "/" + escape(key)
            if key not in local:
                lines.append("missing %s" % child)
            else:
                describe(desired[key], local[key], child, lines)
        for key in local:
            if key not in desired:
                lines.append("UNEXPECTED %s" % (pointer + "/" + escape(key)))
    elif isinstance(desired, list) and isinstance(local, list):
        if not same_json(desired, local):
            lines.append("differs %s" % pointer)
            desired_keys = [json.dumps(i, sort_keys=True) for i in desired]
            local_keys = [json.dumps(i, sort_keys=True) for i in local]
            extra = [i for i, k in zip(local, local_keys) if k not in desired_keys]
            lost = [i for i, k in zip(desired, desired_keys) if k not in local_keys]
            for item in extra:
                lines.append("  + %s (local only)" % json.dumps(item, ensure_ascii=False))
            for item in lost:
                lines.append("  - %s (repository)" % json.dumps(item, ensure_ascii=False))
            if not extra and not lost:
                lines.append("  (same entries, different order or types)")
    elif not same_json(desired, local):
        lines.append("differs %s" % pointer)


def _reject_constant(name):
    raise ValueError("non-finite number %s is not valid JSON" % name)


def parse_json_object(path, label):
    """Return (data, raw_bytes, problem). Fails closed on anything odd."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (OSError, ValueError, RecursionError) as exc:
        return None, None, "invalid JSON in %s: %s" % (label, exc.__class__.__name__ + ": " + str(exc)[:120])
    if not isinstance(data, dict):
        return None, None, "invalid JSON in %s: top level must be an object" % label
    return data, raw, None


def plan_settings(repo_dir, target_dir, policy):
    """Compute what to do with settings.json. Raises ConfigError on bad input."""
    source = os.path.join(repo_dir, SETTINGS)
    destination = os.path.join(target_dir, SETTINGS)
    repo, _, problem = parse_json_object(source, "repository " + SETTINGS)
    if problem:
        raise ConfigError(problem)
    plan = {
        "repo": repo,
        "details": [],
        "invalid": None,
        "desired": repo,
        "action": "none",
        "original": None,
    }
    if not os.path.lexists(destination):
        plan["action"] = "copy"
        return plan
    local, raw, problem = parse_json_object(destination, "installed " + SETTINGS)
    if problem:
        plan["invalid"] = problem
        plan["action"] = "blocked"
        return plan
    desired = merge(repo, local, "", policy)
    describe(desired, local, "", plan["details"])
    plan["desired"] = desired
    plan["original"] = raw
    plan["action"] = "none" if same_json(desired, local) else "write"
    return plan


def required_plugins(repo):
    plugins = repo.get("enabledPlugins")
    if not isinstance(plugins, dict):
        return []
    return sorted(name for name, enabled in plugins.items() if enabled is True)


def plugin_findings(repo, target_dir):
    """Return (missing, unknown_reason); unknown_reason is None when readable."""
    required = required_plugins(repo)
    if not required:
        return [], None
    path = os.path.join(target_dir, PLUGIN_REGISTRY)
    try:
        with open(path, encoding="utf-8") as handle:
            registry = json.load(handle)
    except (OSError, ValueError, RecursionError) as exc:
        return [], "cannot read %s: %s" % (PLUGIN_REGISTRY, exc.__class__.__name__)
    installed = registry.get("plugins") if isinstance(registry, dict) else None
    if not isinstance(installed, dict):
        return [], "unexpected format in %s" % PLUGIN_REGISTRY
    return [name for name in required if name not in installed], None


def atomic_write(path, text, mode):
    directory = os.path.dirname(path)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=directory, prefix=".settings.", suffix=".tmp", delete=False
    )
    try:
        # Restrict the temporary file before any content is written.
        os.chmod(handle.name, mode & 0o700)
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(handle.name, mode)
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------
# Backups and modes


class Backups:
    """Creates one private, never-reused backup directory on first use."""

    def __init__(self, target_dir):
        self.target_dir = target_dir
        self.root = None

    def _mkdir_private(self, path):
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass

    def _create_root(self):
        base_dir = os.path.join(self.target_dir, "backups")
        os.makedirs(self.target_dir, exist_ok=True)
        self._mkdir_private(base_dir)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        base = os.path.join(base_dir, "claude-global-config-" + stamp)
        candidate, counter = base, 1
        while True:
            try:
                os.mkdir(candidate, 0o700)
                return candidate
            except FileExistsError:
                candidate = "%s-%d" % (base, counter)
                counter += 1

    def save(self, rel, destination):
        if self.root is None:
            self.root = self._create_root()
        parts = rel.split("/")
        current = self.root
        for part in parts[:-1]:
            current = os.path.join(current, part)
            self._mkdir_private(current)
        shutil.copy2(destination, os.path.join(current, parts[-1]))


def wanted_mode(rel, source, current):
    """The tightest-only mode for a managed file; never loosens anything."""
    new = current
    if rel == SETTINGS:
        new &= ~0o077
    new &= ~0o022
    if os.stat(source).st_mode & stat.S_IXUSR:
        new |= stat.S_IXUSR
    return new


# --------------------------------------------------------------------------
# Installer


def run(mode, link_bin, out, err):
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    home = os.path.expanduser("~")
    target_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
    local_bin_dir = os.environ.get("LOCAL_BIN_DIR") or os.path.join(home, ".local", "bin")

    # Validate every input before touching the destination, so a bad manifest,
    # policy, or settings file never leaves a partial installation behind.
    entries = read_manifest(repo_dir)
    for rel in entries:
        check_source(repo_dir, os.path.join(repo_dir, rel))
    check_destinations(entries, target_dir)
    policy = load_policy(repo_dir)
    settings_plan = plan_settings(repo_dir, target_dir, policy) if SETTINGS in entries else None
    if settings_plan and settings_plan["invalid"] and mode != "check":
        raise ConfigError("Refusing to overwrite %s: %s" % (SETTINGS, settings_plan["invalid"]))

    backups = Backups(target_dir)
    changed = False
    for rel in entries:
        source = os.path.join(repo_dir, rel)
        destination = os.path.join(target_dir, rel)
        details = []
        if rel == SETTINGS:
            action = settings_plan["action"]
            details = settings_plan["details"]
            if action == "blocked":
                changed = True
                out.write("DIFF %s\n" % rel)
                out.write("  %s\n" % settings_plan["invalid"])
                continue
            if action == "none":
                continue
        elif same_file(source, destination):
            continue
        changed = True
        if mode == "check":
            out.write("DIFF %s\n" % rel)
            for line in details:
                out.write("  %s\n" % line)
            continue
        if mode == "dry-run":
            out.write("INSTALL %s\n" % rel)
            for line in details:
                out.write("  %s\n" % line)
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if os.path.lexists(destination):
            backups.save(rel, destination)
        if rel == SETTINGS and settings_plan["action"] == "write":
            real = os.path.realpath(destination)
            with open(real, "rb") as handle:
                if handle.read() != settings_plan["original"]:
                    raise ConfigError(
                        "%s changed during installation; nothing was written, rerun the installer"
                        % SETTINGS
                    )
            text = json.dumps(settings_plan["desired"], indent=2, ensure_ascii=False, allow_nan=False) + "\n"
            atomic_write(real, text, os.stat(real).st_mode & 0o7777)
        elif rel == SETTINGS:
            # Fresh install: verbatim repository content, created private.
            with open(source, encoding="utf-8", newline="") as handle:
                atomic_write(destination, handle.read(), 0o600)
        else:
            shutil.copy2(source, destination)
        out.write("Installed %s\n" % rel)
        for line in details:
            out.write("  %s\n" % line)

    # File modes: only ever tightened, or the owner execute bit restored.
    for rel in entries:
        source = os.path.join(repo_dir, rel)
        destination = os.path.join(target_dir, rel)
        if not os.path.isfile(destination):
            continue
        current = stat.S_IMODE(os.stat(destination).st_mode)
        wanted = wanted_mode(rel, source, current)
        if wanted == current:
            continue
        changed = True
        if mode == "install":
            os.chmod(destination, wanted)
            out.write("Mode %s %03o -> %03o\n" % (rel, current, wanted))
        else:
            out.write("MODE %s %03o (expected %03o)\n" % (rel, current, wanted))

    # Required plugins must be present, not merely enabled.
    if settings_plan:
        missing, unknown = plugin_findings(settings_plan["repo"], target_dir)
        if unknown:
            err.write("UNKNOWN plugin state: %s\n" % unknown)
        for name in missing:
            if mode == "check":
                changed = True
                out.write("MISSING-PLUGIN %s\n" % name)
            else:
                err.write("warning: required plugin is not installed: %s\n" % name)

    if mode == "check":
        if not changed:
            out.write("Configuration matches the tracked repository.\n")
            return 0
        return 1

    if link_bin:
        for helper in HELPERS:
            link_path = os.path.join(local_bin_dir, helper)
            helper_path = os.path.join(target_dir, "bin", helper)
            if os.path.lexists(link_path) and not os.path.islink(link_path):
                err.write(
                    "Skipped %s: an existing non-symlink file is in the way.\n" % link_path
                )
                continue
            if mode == "dry-run":
                out.write("LINK %s -> %s\n" % (link_path, helper_path))
                continue
            os.makedirs(local_bin_dir, exist_ok=True)
            if os.path.islink(link_path):
                os.unlink(link_path)
            os.symlink(helper_path, link_path)

    if mode == "install" and not changed:
        out.write("Configuration already matches the tracked repository.\n")
    if mode == "install" and backups.root:
        out.write("Previous files were backed up to %s\n" % backups.root)
    return 0


def main(argv=None, out=sys.stdout, err=sys.stderr):
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = "install"
    link_bin = True
    for arg in argv:
        if arg == "--dry-run":
            mode = "dry-run"
        elif arg == "--check":
            mode = "check"
        elif arg == "--no-link-bin":
            link_bin = False
        elif arg in ("-h", "--help"):
            out.write(USAGE)
            return 0
        else:
            err.write("Unknown option: %s\n" % safe_text(arg))
            err.write(USAGE)
            return 2
    out, err = SafeStream(out), SafeStream(err)
    try:
        return run(mode, link_bin, out, err)
    except ConfigError as exc:
        err.write("%s\n" % exc)
        return 2
    except OSError as exc:
        err.write("error: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
