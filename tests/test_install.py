"""Characterization tests for the configuration installer.

The installer under test is selected with INSTALLER (default: install.py).
Each test builds a throwaway repository containing a copy of the installer,
a small manifest, and sample files, so nothing touches the real ~/.claude.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.environ.get("INSTALLER", "install.py")

MANIFEST = """# comment line

CLAUDE.md
settings.json
agents/one.md
bin/claude-workflow
bin/remote-runner
"""

FILES = {
    "CLAUDE.md": "policy\n",
    "settings.json": "{}\n",
    "agents/one.md": "agent\n",
    "bin/claude-workflow": "#!/bin/sh\necho cw\n",
    "bin/remote-runner": "#!/bin/sh\necho rr\n",
}


class InstallerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = self.tmp.name
        self.repo = os.path.join(base, "repo")
        self.config = os.path.join(base, "claude")
        self.bin = os.path.join(base, "localbin")
        os.makedirs(self.repo)
        shutil.copy2(os.path.join(ROOT, INSTALLER), os.path.join(self.repo, INSTALLER))
        self.write_repo("config-manifest.txt", MANIFEST)
        for rel, text in FILES.items():
            self.write_repo(rel, text)
        os.chmod(os.path.join(self.repo, "bin/claude-workflow"), 0o755)
        os.chmod(os.path.join(self.repo, "bin/remote-runner"), 0o755)

    # -- helpers ------------------------------------------------------

    def write_repo(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(text)

    def run_installer(self, *args):
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = self.config
        env["LOCAL_BIN_DIR"] = self.bin
        script = os.path.join(self.repo, INSTALLER)
        if INSTALLER.endswith(".py"):
            cmd = [sys.executable, "-I", script] + list(args)
        else:
            cmd = ["sh", script] + list(args)
        return subprocess.run(cmd, env=env, text=True, capture_output=True, cwd=self.repo)

    def dest(self, rel):
        return os.path.join(self.config, rel)

    def read(self, path):
        with open(path) as handle:
            return handle.read()

    def backups(self):
        root = os.path.join(self.config, "backups")
        if not os.path.isdir(root):
            return []
        return sorted(os.listdir(root))


class InstallerTest(InstallerBase):
    # -- install ------------------------------------------------------

    def test_fresh_install_copies_manifest_files(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        for rel, text in FILES.items():
            self.assertEqual(self.read(self.dest(rel)), text)
            self.assertIn("Installed %s" % rel, result.stdout)
        self.assertEqual(self.backups(), [])

    def test_install_links_helpers(self):
        self.run_installer()
        for helper in ("claude-workflow", "remote-runner"):
            link = os.path.join(self.bin, helper)
            self.assertTrue(os.path.islink(link))
            self.assertEqual(os.readlink(link), os.path.join(self.config, "bin", helper))

    def test_no_link_bin(self):
        result = self.run_installer("--no-link-bin")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.exists(self.bin))

    def test_second_run_is_idempotent(self):
        self.run_installer()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Configuration already matches the tracked repository.", result.stdout)
        self.assertNotIn("Installed", result.stdout)
        self.assertEqual(self.backups(), [])

    def test_changed_destination_is_backed_up(self):
        self.run_installer()
        with open(self.dest("CLAUDE.md"), "w") as handle:
            handle.write("local edit\n")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read(self.dest("CLAUDE.md")), "policy\n")
        self.assertIn("Installed CLAUDE.md", result.stdout)
        self.assertIn("Previous files were backed up to", result.stdout)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith("claude-global-config-"))
        saved = os.path.join(self.config, "backups", backups[0], "CLAUDE.md")
        self.assertEqual(self.read(saved), "local edit\n")

    def test_unmanaged_files_untouched(self):
        os.makedirs(self.config)
        with open(os.path.join(self.config, "history.jsonl"), "w") as handle:
            handle.write("private\n")
        self.run_installer()
        self.assertEqual(self.read(os.path.join(self.config, "history.jsonl")), "private\n")

    def test_modes_preserved(self):
        self.run_installer()
        mode = os.stat(self.dest("bin/claude-workflow")).st_mode
        self.assertTrue(mode & stat.S_IXUSR)

    # -- dry run ------------------------------------------------------

    def test_dry_run_writes_nothing(self):
        result = self.run_installer("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INSTALL CLAUDE.md", result.stdout)
        self.assertIn("LINK ", result.stdout)
        self.assertFalse(os.path.exists(self.config))
        self.assertFalse(os.path.exists(self.bin))

    # -- check --------------------------------------------------------

    def test_check_reports_missing_as_diff(self):
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DIFF CLAUDE.md", result.stdout)
        self.assertFalse(os.path.exists(self.config))

    def test_check_matches_after_install(self):
        self.run_installer()
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Configuration matches the tracked repository.", result.stdout)

    def test_check_reports_drift(self):
        self.run_installer()
        with open(self.dest("agents/one.md"), "w") as handle:
            handle.write("changed\n")
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DIFF agents/one.md", result.stdout)
        self.assertNotIn("DIFF CLAUDE.md", result.stdout)
        self.assertEqual(self.read(self.dest("agents/one.md")), "changed\n")

    # -- refusals -----------------------------------------------------

    def test_unsafe_manifest_paths_rejected(self):
        for bad in ("/etc/passwd", "../outside", "a/../b", "a/.."):
            with self.subTest(path=bad):
                self.write_repo("config-manifest.txt", bad + "\n")
                result = self.run_installer()
                self.assertEqual(result.returncode, 2)
                self.assertIn("Unsafe manifest path", result.stderr)

    def test_missing_source_rejected(self):
        self.write_repo("config-manifest.txt", "nope.md\n")
        result = self.run_installer()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Missing source file", result.stderr)

    def test_unknown_option(self):
        result = self.run_installer("--bogus")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown option", result.stderr)
        self.assertIn("Usage:", result.stderr)

    def test_help(self):
        result = self.run_installer("-h")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)

    def test_non_symlink_in_the_way_is_skipped(self):
        os.makedirs(self.bin)
        blocker = os.path.join(self.bin, "claude-workflow")
        with open(blocker, "w") as handle:
            handle.write("mine\n")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Skipped", result.stderr)
        self.assertFalse(os.path.islink(blocker))
        self.assertEqual(self.read(blocker), "mine\n")
        self.assertTrue(os.path.islink(os.path.join(self.bin, "remote-runner")))


POLICY = """# settings policy
preference /advisorModel
preference /theme
preference /model
preference /modelSettings
preference /uiPrefs/compact
open /enabledPlugins
"""

REPO_SETTINGS = {
    "uiPrefs": {"compact": False, "other": 1},
    "permissions": {"defaultMode": "auto", "allow": ["Bash(ls:*)", "Bash(pytest:*)"], "deny": ["Read(.env)"]},
    "enabledPlugins": {"superpowers@claude-plugins-official": True},
    "advisorModel": "opus",
    "theme": "dark",
}


@unittest.skipIf(INSTALLER.endswith(".sh"), "settings policy exists only in install.py")
class SettingsPolicyTest(InstallerBase):
    def setUp(self):
        super().setUp()
        self.set_repo(REPO_SETTINGS)
        self.write_repo("settings-policy.txt", POLICY)

    def set_repo(self, data):
        self.write_repo("settings.json", json.dumps(data, indent=2) + "\n")

    def set_local(self, data, raw=None):
        """Install the other managed files, then write the local settings."""
        for rel in FILES:
            if rel == "settings.json":
                continue
            target = self.dest(rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(self.repo, rel), target)
        os.makedirs(self.config, exist_ok=True)
        with open(self.dest("settings.json"), "w") as handle:
            handle.write(raw if raw is not None else json.dumps(data, indent=2) + "\n")
        os.chmod(self.dest("settings.json"), 0o600)  # as Claude Code itself leaves it

    def local(self):
        with open(self.dest("settings.json")) as handle:
            return json.load(handle)

    def registry(self, plugins):
        os.makedirs(os.path.join(self.config, "plugins"), exist_ok=True)
        with open(os.path.join(self.config, "plugins", "installed_plugins.json"), "w") as handle:
            json.dump({"version": 2, "plugins": {p: [{"scope": "user"}] for p in plugins}}, handle)

    def merged_local(self, **changes):
        data = json.loads(json.dumps(REPO_SETTINGS))
        data.update(changes)
        return data

    # -- install semantics --------------------------------------------

    def test_fresh_install_copies_repo_file_verbatim(self):
        self.run_installer("--no-link-bin")
        self.assertEqual(self.read(self.dest("settings.json")), self.read(os.path.join(self.repo, "settings.json")))

    def test_absent_preference_is_seeded(self):
        local = self.merged_local()
        del local["theme"]
        self.set_local(local)
        self.run_installer("--no-link-bin")
        self.assertEqual(self.local()["theme"], "dark")

    def test_local_preference_value_is_kept_and_not_drift(self):
        self.set_local(self.merged_local(theme="light", advisorModel="sonnet"))
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.run_installer("--no-link-bin")
        self.assertEqual(self.local()["theme"], "light")
        self.assertEqual(self.local()["advisorModel"], "sonnet")

    def test_nested_preference_path(self):
        local = self.merged_local()
        local["uiPrefs"] = dict(local["uiPrefs"], compact=True)
        self.set_local(local)
        self.assertEqual(self.run_installer("--check").returncode, 0)
        self.run_installer("--no-link-bin")
        self.assertEqual(self.local()["uiPrefs"]["compact"], True)
        local["uiPrefs"]["other"] = 99
        self.set_local(local)
        self.assertEqual(self.run_installer("--check").returncode, 1)

    def test_local_only_preferences_not_in_repo_are_kept(self):
        self.set_local(self.merged_local(model="sonnet", modelSettings={"x": {"effortLevel": "high"}}))
        self.assertEqual(self.run_installer("--check").returncode, 0)
        self.run_installer("--no-link-bin")
        self.assertEqual(self.local()["model"], "sonnet")
        self.assertEqual(self.local()["modelSettings"], {"x": {"effortLevel": "high"}})

    def test_open_map_keeps_extra_plugins_and_enforces_repo_entries(self):
        local = self.merged_local()
        local["enabledPlugins"] = {"superpowers@claude-plugins-official": False, "clangd-lsp@x": True}
        self.set_local(local)
        self.registry(["superpowers@claude-plugins-official"])
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("/enabledPlugins/superpowers@claude-plugins-official", check.stdout)
        self.run_installer("--no-link-bin")
        plugins = self.local()["enabledPlugins"]
        self.assertTrue(plugins["superpowers@claude-plugins-official"])
        self.assertTrue(plugins["clangd-lsp@x"])

    def test_extra_plugins_alone_are_not_drift(self):
        local = self.merged_local()
        local["enabledPlugins"] = dict(local["enabledPlugins"], **{"anything@synced": False, "other@m": True})
        self.set_local(local)
        self.registry(["superpowers@claude-plugins-official"])
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_strict_list_difference_is_drift_and_backed_up(self):
        local = self.merged_local()
        local["permissions"] = dict(local["permissions"], allow=["Bash(ls:*)", "Bash(rm:*)"])
        self.set_local(local)
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("DIFF settings.json", check.stdout)
        self.assertIn("/permissions/allow", check.stdout)
        self.assertIn("Bash(rm:*)", check.stdout)
        self.assertIn("Bash(pytest:*)", check.stdout)
        self.run_installer("--no-link-bin")
        self.assertEqual(self.local()["permissions"]["allow"], ["Bash(ls:*)", "Bash(pytest:*)"])
        saved = os.path.join(self.config, "backups", self.backups()[0], "settings.json")
        self.assertIn("Bash(rm:*)", self.read(saved))

    def test_unexpected_local_key_fails_check_and_is_dropped_on_install(self):
        self.set_local(self.merged_local(enableAllProjectMcpServers=True))
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("UNEXPECTED /enableAllProjectMcpServers", check.stdout)
        self.run_installer("--no-link-bin")
        self.assertNotIn("enableAllProjectMcpServers", self.local())
        saved = os.path.join(self.config, "backups", self.backups()[0], "settings.json")
        self.assertIn("enableAllProjectMcpServers", self.read(saved))

    def test_missing_strict_key_is_drift_and_restored(self):
        local = self.merged_local()
        del local["permissions"]["deny"]
        self.set_local(local)
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("missing /permissions/deny", check.stdout)
        self.run_installer("--no-link-bin")
        self.assertEqual(self.local()["permissions"]["deny"], ["Read(.env)"])

    def test_install_is_idempotent(self):
        self.set_local(self.merged_local(model="sonnet", enableAllProjectMcpServers=True))
        self.run_installer("--no-link-bin")
        first = self.read(self.dest("settings.json"))
        backups = self.backups()
        result = self.run_installer("--no-link-bin")
        self.assertIn("Configuration already matches the tracked repository.", result.stdout)
        self.assertEqual(self.read(self.dest("settings.json")), first)
        self.assertEqual(self.backups(), backups)
        self.assertEqual(self.run_installer("--check").returncode, 0)

    def test_formatting_only_difference_is_not_drift(self):
        self.set_local(None, raw=json.dumps(self.merged_local()))
        self.assertEqual(self.run_installer("--check").returncode, 0)

    # -- safety -------------------------------------------------------

    def test_malformed_local_json_is_never_overwritten(self):
        self.set_local(None, raw="{not json")
        result = self.run_installer("--no-link-bin")
        self.assertEqual(result.returncode, 2)
        self.assertIn("settings.json", result.stderr)
        self.assertEqual(self.read(self.dest("settings.json")), "{not json")
        self.assertEqual(self.backups(), [])
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("invalid JSON", check.stdout)

    def test_non_object_local_json_is_refused(self):
        self.set_local(None, raw="[1, 2]\n")
        result = self.run_installer("--no-link-bin")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.read(self.dest("settings.json")), "[1, 2]\n")

    def test_malformed_repo_json_refused_before_any_write(self):
        self.write_repo("settings.json", "{oops")
        result = self.run_installer("--no-link-bin")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(os.path.exists(self.dest("CLAUDE.md")))

    def test_bad_policy_file_refused(self):
        for bad in ("bogus /theme\n", "preference theme\n", "preference\n", "open /a/../b\n"):
            with self.subTest(policy=bad):
                self.write_repo("settings-policy.txt", bad)
                result = self.run_installer("--no-link-bin")
                self.assertEqual(result.returncode, 2)
                self.assertIn("settings-policy.txt", result.stderr)

    def test_no_temp_files_left_and_mode_preserved(self):
        self.set_local(self.merged_local(theme="light", advisorModel="x"))
        os.chmod(self.dest("settings.json"), 0o600)
        local = self.merged_local()
        local["permissions"] = dict(local["permissions"], deny=[])
        self.set_local(local)
        os.chmod(self.dest("settings.json"), 0o600)
        self.run_installer("--no-link-bin")
        self.assertEqual(stat.S_IMODE(os.stat(self.dest("settings.json")).st_mode), 0o600)
        leftovers = [n for n in os.listdir(self.config) if n.startswith(".") or n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_symlinked_settings_target_is_updated_in_place(self):
        real = os.path.join(self.tmp.name, "real-settings.json")
        local = self.merged_local()
        local["permissions"] = dict(local["permissions"], deny=[])
        with open(real, "w") as handle:
            json.dump(local, handle)
        os.makedirs(self.config)
        os.symlink(real, self.dest("settings.json"))
        self.run_installer("--no-link-bin")
        self.assertTrue(os.path.islink(self.dest("settings.json")))
        with open(real) as handle:
            self.assertEqual(json.load(handle)["permissions"]["deny"], ["Read(.env)"])

    def test_dry_run_reports_detail_and_writes_nothing(self):
        local = self.merged_local()
        local["permissions"] = dict(local["permissions"], allow=[])
        self.set_local(local)
        before = self.read(self.dest("settings.json"))
        result = self.run_installer("--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("INSTALL settings.json", result.stdout)
        self.assertIn("/permissions/allow", result.stdout)
        self.assertEqual(self.read(self.dest("settings.json")), before)

    # -- plugin presence ----------------------------------------------

    def test_required_plugin_missing_from_registry_fails_check(self):
        self.set_local(self.merged_local())
        self.registry(["somethingelse@m"])
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("MISSING-PLUGIN superpowers@claude-plugins-official", result.stdout)

    def test_required_plugin_present_passes(self):
        self.set_local(self.merged_local())
        self.registry(["superpowers@claude-plugins-official"])
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unknown_plugin_state_warns_but_does_not_fail(self):
        self.set_local(self.merged_local())
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("UNKNOWN plugin state", result.stderr)
        os.makedirs(os.path.join(self.config, "plugins"))
        with open(os.path.join(self.config, "plugins", "installed_plugins.json"), "w") as handle:
            handle.write("[]")
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("UNKNOWN plugin state", result.stderr)

    def test_disabled_repo_plugin_is_not_required(self):
        data = json.loads(json.dumps(REPO_SETTINGS))
        data["enabledPlugins"]["off@m"] = False
        self.set_repo(data)
        self.set_local(data)
        self.registry(["superpowers@claude-plugins-official"])
        self.assertEqual(self.run_installer("--check").returncode, 0)

    def test_install_warns_when_required_plugin_not_installed(self):
        self.registry([])
        result = self.run_installer("--no-link-bin")
        self.assertEqual(result.returncode, 0)
        self.assertIn("superpowers@claude-plugins-official", result.stderr)


def load_installer_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("installer_under_test", os.path.join(ROOT, "install.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(INSTALLER.endswith(".sh"), "security hardening exists only in install.py")
class SecurityTest(InstallerBase):
    """Regression tests for findings from the security review."""

    def setUp(self):
        super().setUp()
        self.write_repo("settings.json", json.dumps(REPO_SETTINGS, indent=2) + "\n")
        self.write_repo("settings-policy.txt", POLICY)

    def install(self, *args):
        return self.run_installer("--no-link-bin", *args)

    # manifest spelling and case must not route settings.json around policy

    def test_non_canonical_manifest_spellings_rejected(self):
        for bad in ("./settings.json", "settings.json/", "agents//one.md", "agents/./one.md"):
            with self.subTest(path=bad):
                self.write_repo("config-manifest.txt", "CLAUDE.md\n" + bad + "\n")
                result = self.install()
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("Unsafe manifest path", result.stderr)
                self.assertFalse(os.path.exists(self.dest("CLAUDE.md")))

    def test_case_variant_of_settings_rejected(self):
        for bad in ("Settings.json", "SETTINGS.JSON"):
            with self.subTest(path=bad):
                self.write_repo("config-manifest.txt", "CLAUDE.md\n" + bad + "\n")
                result = self.install()
                self.assertEqual(result.returncode, 2)
                self.assertIn("settings.json", result.stderr)
                self.assertFalse(os.path.exists(self.dest("CLAUDE.md")))

    def test_duplicate_manifest_entries_rejected(self):
        self.write_repo("config-manifest.txt", "CLAUDE.md\nclaude.md\n")
        result = self.install()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Duplicate manifest path", result.stderr)

    # sources must be regular files inside the repository

    def test_symlinked_source_rejected(self):
        outside = os.path.join(self.tmp.name, "outside.txt")
        with open(outside, "w") as handle:
            handle.write("secret\n")
        os.unlink(os.path.join(self.repo, "agents/one.md"))
        os.symlink(outside, os.path.join(self.repo, "agents/one.md"))
        result = self.install()
        self.assertEqual(result.returncode, 2)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(os.path.exists(self.dest("agents/one.md")))
        self.assertFalse(os.path.exists(self.dest("CLAUDE.md")))

    def test_symlinked_settings_and_policy_rejected(self):
        outside = os.path.join(self.tmp.name, "other.json")
        with open(outside, "w") as handle:
            handle.write("{}")
        os.unlink(os.path.join(self.repo, "settings.json"))
        os.symlink(outside, os.path.join(self.repo, "settings.json"))
        self.assertEqual(self.install().returncode, 2)
        self.write_repo("settings.json", json.dumps(REPO_SETTINGS))
        os.unlink(os.path.join(self.repo, "settings-policy.txt"))
        os.symlink(outside, os.path.join(self.repo, "settings-policy.txt"))
        self.assertEqual(self.install().returncode, 2)

    def test_source_through_symlinked_directory_outside_repo_rejected(self):
        outside = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(outside)
        with open(os.path.join(outside, "one.md"), "w") as handle:
            handle.write("x\n")
        shutil.rmtree(os.path.join(self.repo, "agents"))
        os.symlink(outside, os.path.join(self.repo, "agents"))
        result = self.install()
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the repository", result.stderr)

    # policy mistakes must not weaken security-relevant settings

    def test_protected_settings_cannot_be_preference_or_open(self):
        for bad in (
            "preference /permissions",
            "open /permissions/allow",
            "preference /permissions/defaultMode",
            "open /hooks",
            "preference /env/ANY",
            "preference /apiKeyHelper",
            "preference /statusLine",
            "preference /enableAllProjectMcpServers",
        ):
            with self.subTest(policy=bad):
                self.write_repo("settings-policy.txt", bad + "\n")
                result = self.install()
                self.assertEqual(result.returncode, 2)
                self.assertIn("protected", result.stderr)

    # terminal output must not carry control characters from local data

    def test_control_characters_in_local_keys_are_neutralized(self):
        data = json.loads(json.dumps(REPO_SETTINGS))
        data["\x1b[31mEVIL\x07"] = 1
        os.makedirs(self.config)
        with open(self.dest("settings.json"), "w") as handle:
            json.dump(data, handle)
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 1)
        for text in (result.stdout, result.stderr):
            self.assertNotIn("\x1b", text)
            self.assertNotIn("\x07", text)
        self.assertIn("EVIL", result.stdout)

    # JSON edge values fail closed

    def test_nan_and_deep_nesting_are_invalid_not_crashes(self):
        os.makedirs(self.config)
        for raw in ('{"a": NaN}', '{"a": Infinity}', "[" * 100000 + "]" * 100000):
            with self.subTest(raw=raw[:20]):
                with open(self.dest("settings.json"), "w") as handle:
                    handle.write(raw)
                result = self.install()
                self.assertEqual(result.returncode, 2, result.stderr[-300:])
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.read(self.dest("settings.json")), raw)
                check = self.run_installer("--check")
                self.assertEqual(check.returncode, 1)
                self.assertNotIn("Traceback", check.stderr)

    def test_nan_in_repository_settings_rejected(self):
        self.write_repo("settings.json", '{"theme": NaN}')
        result = self.install()
        self.assertEqual(result.returncode, 2)

    # backups are never overwritten

    def test_same_second_installs_keep_both_backups(self):
        module = load_installer_module()
        os.environ["CLAUDE_CONFIG_DIR"] = self.config
        os.environ["LOCAL_BIN_DIR"] = self.bin
        module.__file__ = os.path.join(self.repo, "install.py")
        module.time.strftime = lambda fmt, t=None: "20260101T000000Z"
        self.addCleanup(lambda: setattr(module.time, "strftime", __import__("time").strftime))
        import io

        def run():
            module.main(["--no-link-bin"], out=io.StringIO(), err=io.StringIO())

        run()
        for version in ("one\n", "two\n"):
            with open(self.dest("CLAUDE.md"), "w") as handle:
                handle.write(version)
            run()
        saved = []
        for name in sorted(os.listdir(os.path.join(self.config, "backups"))):
            path = os.path.join(self.config, "backups", name, "CLAUDE.md")
            if os.path.exists(path):
                saved.append(self.read(path))
        self.assertEqual(sorted(saved), ["one\n", "two\n"])

    # settings.json changed between planning and writing

    def test_concurrent_change_is_detected_not_overwritten(self):
        module = load_installer_module()
        import io

        os.makedirs(self.config)
        data = json.loads(json.dumps(REPO_SETTINGS))
        data["permissions"]["deny"] = []
        with open(self.dest("settings.json"), "w") as handle:
            json.dump(data, handle)
        os.environ["CLAUDE_CONFIG_DIR"] = self.config
        os.environ["LOCAL_BIN_DIR"] = self.bin
        module.__file__ = os.path.join(self.repo, "install.py")
        original_copy2 = module.shutil.copy2

        def racing_copy2(src, dst, *args, **kwargs):
            result = original_copy2(src, dst, *args, **kwargs)
            if os.path.basename(src) == "settings.json" and "backups" in dst:
                with open(self.dest("settings.json"), "w") as handle:
                    handle.write('{"changed": "concurrently"}')
            return result

        module.shutil.copy2 = racing_copy2
        self.addCleanup(lambda: setattr(module.shutil, "copy2", original_copy2))
        err = io.StringIO()
        code = module.main(["--no-link-bin"], out=io.StringIO(), err=err)
        self.assertEqual(code, 2)
        self.assertIn("changed during installation", err.getvalue())
        self.assertEqual(self.read(self.dest("settings.json")), '{"changed": "concurrently"}')

    # findings from the independent adversarial review

    def test_more_command_executing_settings_are_protected(self):
        for key in ("fileSuggestion", "extraKnownMarketplaces", "otelHeadersHelper", "gcpAuthRefresh",
                    "sandbox", "disableAllHooks", "skipDangerousModePermissionPrompt",
                    "allowedMcpServers"):
            with self.subTest(key=key):
                self.write_repo("settings-policy.txt", "preference /%s\n" % key)
                result = self.install()
                self.assertEqual(result.returncode, 2)
                self.assertIn("protected", result.stderr)

    def test_duplicate_or_contradictory_policy_lines_rejected(self):
        for text in ("preference /model\npreference /model\n", "preference /model\nopen /model\n"):
            with self.subTest(policy=text):
                self.write_repo("settings-policy.txt", text)
                result = self.install()
                self.assertEqual(result.returncode, 2)
                self.assertIn("duplicate", result.stderr.lower())

    def test_python_equal_json_values_are_still_drift(self):
        self.write_repo("settings.json", json.dumps({"flag": False, "n": 1, "l": [False, 1]}))
        self.write_repo("settings-policy.txt", "")
        self.assertEqual(self.install().returncode, 0)
        with open(self.dest("settings.json"), "w") as handle:
            handle.write('{"flag": 0, "n": true, "l": [0, 1.0]}')
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1, check.stdout)
        self.assertIn("/flag", check.stdout)
        self.assertIn("/n", check.stdout)
        self.assertIn("/l", check.stdout)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.run_installer("--check").returncode, 0)

    def test_invalid_utf8_inputs_exit_2_without_traceback(self):
        for name in ("config-manifest.txt", "settings-policy.txt"):
            with self.subTest(file=name):
                original = self.read(os.path.join(self.repo, name))
                with open(os.path.join(self.repo, name), "wb") as handle:
                    handle.write(b"\xff\xfe\n")
                for args in (("--check",), ("--dry-run",), ()):
                    result = self.run_installer("--no-link-bin", *args)
                    self.assertEqual(result.returncode, 2, args)
                    self.assertNotIn("Traceback", result.stderr)
                self.write_repo(name, original)

    def test_destination_alias_cannot_overwrite_policy_managed_settings(self):
        os.makedirs(self.config)
        os.symlink(".", os.path.join(self.config, "x"))
        with open(self.dest("settings.json"), "w") as handle:
            handle.write('{"sentinel": true}')
        self.write_repo("x/settings.json", '{"hooks": 1}')
        self.write_repo("config-manifest.txt", "CLAUDE.md\nsettings.json\nx/settings.json\n")
        result = self.install()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.read(self.dest("settings.json")), '{"sentinel": true}')
        self.assertFalse(os.path.exists(self.dest("CLAUDE.md")))

    def test_destination_parent_symlink_outside_config_rejected(self):
        outside = os.path.join(self.tmp.name, "outside-dir")
        os.makedirs(outside)
        os.makedirs(self.config)
        os.symlink(outside, os.path.join(self.config, "agents"))
        result = self.install()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(os.listdir(outside), [])

    # unexpected I/O failures are reported, not tracebacks

    def test_os_errors_are_reported_cleanly(self):
        with open(self.config, "w") as handle:  # a file where the directory should be
            handle.write("x")
        result = self.install()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("error:", result.stderr)


@unittest.skipIf(INSTALLER.endswith(".sh"), "mode rules exist only in install.py")
class ModeRulesTest(InstallerBase):
    """File permission rules: only ever tighten, or restore the owner x bit."""

    def setUp(self):
        super().setUp()
        self.write_repo("settings.json", json.dumps(REPO_SETTINGS, indent=2) + "\n")
        self.write_repo("settings-policy.txt", POLICY)

    def mode(self, rel):
        return stat.S_IMODE(os.stat(self.dest(rel)).st_mode)

    def install(self, *args):
        return self.run_installer("--no-link-bin", *args)

    def test_fresh_settings_is_private_even_though_repo_file_is_not(self):
        os.chmod(os.path.join(self.repo, "settings.json"), 0o644)
        self.install()
        self.assertEqual(self.mode("settings.json"), 0o600)
        self.assertEqual(self.mode("CLAUDE.md") & 0o022, 0)
        self.assertTrue(self.mode("bin/claude-workflow") & 0o100)

    def test_correct_modes_check_clean(self):
        self.install()
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("MODE", result.stdout)

    def test_loose_settings_reported_and_tightened_without_backup(self):
        self.install()
        os.chmod(self.dest("settings.json"), 0o644)
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("MODE settings.json", check.stdout)
        before = self.read(self.dest("settings.json"))
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mode("settings.json"), 0o600)
        self.assertEqual(self.read(self.dest("settings.json")), before)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.run_installer("--check").returncode, 0)

    def test_lost_executable_bit_restored(self):
        self.install()
        os.chmod(self.dest("bin/claude-workflow"), 0o644)
        check = self.run_installer("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("MODE bin/claude-workflow", check.stdout)
        self.install()
        self.assertTrue(self.mode("bin/claude-workflow") & 0o100)
        self.assertEqual(self.mode("bin/claude-workflow") & 0o022, 0)

    def test_group_and_world_write_removed(self):
        self.install()
        for bits in (0o664, 0o666, 0o646):
            with self.subTest(mode=oct(bits)):
                os.chmod(self.dest("CLAUDE.md"), bits)
                self.assertEqual(self.run_installer("--check").returncode, 1)
                self.install()
                self.assertEqual(self.mode("CLAUDE.md"), bits & ~0o022)

    def test_never_loosens(self):
        self.install()
        os.chmod(self.dest("settings.json"), 0o400)
        os.chmod(self.dest("CLAUDE.md"), 0o600)
        self.assertEqual(self.run_installer("--check").returncode, 0)
        self.install()
        self.assertEqual(self.mode("settings.json"), 0o400)
        self.assertEqual(self.mode("CLAUDE.md"), 0o600)

    def test_non_executable_source_never_gains_exec(self):
        self.install()
        os.chmod(self.dest("CLAUDE.md"), 0o644)
        self.install()
        self.assertEqual(self.mode("CLAUDE.md") & 0o111, 0)

    def test_dry_run_reports_modes_and_changes_nothing(self):
        self.install()
        os.chmod(self.dest("settings.json"), 0o644)
        result = self.run_installer("--dry-run")
        self.assertEqual(result.returncode, 0)
        self.assertIn("MODE settings.json", result.stdout)
        self.assertEqual(self.mode("settings.json"), 0o644)

    def test_merge_write_preserves_privacy_and_tightens_loose_mode(self):
        self.install()
        data = json.loads(self.read(self.dest("settings.json")))
        data["permissions"]["deny"] = []
        with open(self.dest("settings.json"), "w") as handle:
            json.dump(data, handle)
        os.chmod(self.dest("settings.json"), 0o664)
        self.install()
        self.assertEqual(self.mode("settings.json"), 0o600)
        self.assertEqual(json.loads(self.read(self.dest("settings.json")))["permissions"]["deny"], ["Read(.env)"])

    def test_backup_directories_are_private(self):
        self.install()
        with open(self.dest("agents/one.md"), "w") as handle:
            handle.write("local\n")
        self.install()
        root = os.path.join(self.config, "backups")
        for dirpath, dirnames, _ in os.walk(root):
            for name in dirnames + [""]:
                path = os.path.join(dirpath, name)
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o077, 0, path)

    def test_second_install_is_idempotent(self):
        self.install()
        result = self.install()
        self.assertIn("Configuration already matches the tracked repository.", result.stdout)
        self.assertNotIn("MODE", result.stdout)


LEGACY = os.path.join(ROOT, "install.sh")
NEW = os.path.join(ROOT, "install.py")


@unittest.skipUnless(
    os.path.isfile(LEGACY) and os.path.isfile(NEW), "needs both install.sh and install.py"
)
class DifferentialTest(unittest.TestCase):
    """install.py must match install.sh on trees and (normalized) output.

    Intentional difference, not compared: a manifest entry with a missing
    source is rejected up front by install.py, whereas install.sh fails
    midway after installing the earlier entries.
    """

    def build(self, name, installer):
        base = tempfile.mkdtemp(prefix="diff-" + name + "-")
        self.addCleanup(shutil.rmtree, base, True)
        repo = os.path.join(base, "repo")
        os.makedirs(repo)
        shutil.copy2(installer, os.path.join(repo, os.path.basename(installer)))
        for rel, text in list(FILES.items()) + [("config-manifest.txt", MANIFEST)]:
            path = os.path.join(repo, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as handle:
                handle.write(text)
        for helper in ("claude-workflow", "remote-runner"):
            os.chmod(os.path.join(repo, "bin", helper), 0o755)
        return base

    def run_one(self, base, installer, args):
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = os.path.join(base, "claude")
        env["LOCAL_BIN_DIR"] = os.path.join(base, "localbin")
        script = os.path.join(base, "repo", os.path.basename(installer))
        cmd = ([sys.executable, "-I", script] if script.endswith(".py") else ["sh", script]) + args
        return subprocess.run(cmd, env=env, text=True, capture_output=True, cwd=os.path.join(base, "repo"))

    @staticmethod
    def normalize(text, base):
        text = text.replace(base, "<TMP>")
        text = re.sub(r"claude-global-config-\d{8}T\d{6}Z", "claude-global-config-<TS>", text)
        return text.replace("install.sh", "install.X").replace("install.py", "install.X")

    @staticmethod
    def snapshot(base):
        result = {}
        for sub in ("claude", "localbin"):
            top = os.path.join(base, sub)
            for dirpath, dirnames, filenames in os.walk(top):
                for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, base)
                    rel = re.sub(r"claude-global-config-\d{8}T\d{6}Z", "claude-global-config-<TS>", rel)
                    if os.path.islink(full):
                        result[rel] = ("link", os.readlink(full).replace(base, "<TMP>"))
                    else:
                        with open(full) as handle:
                            mode = os.stat(full).st_mode & 0o777
                            if os.path.basename(full) == "settings.json":
                                mode &= 0o111  # install.py intentionally makes it 0600
                            result[rel] = ("file", handle.read(), mode)
        return result

    def scenario(self, steps):
        sh_base, py_base = self.build("sh", LEGACY), self.build("py", NEW)
        for step in steps:
            for base, installer in ((sh_base, LEGACY), (py_base, NEW)):
                if callable(step):
                    step(base)
                    continue
                result = self.run_one(base, installer, step)
                if base is sh_base:
                    expected = (result.returncode, self.normalize(result.stdout, base),
                                self.normalize(result.stderr, base))
                else:
                    actual = (result.returncode, self.normalize(result.stdout, base),
                              self.normalize(result.stderr, base))
                    self.assertEqual(expected, actual, "args=%r" % (step,))
        self.assertEqual(self.snapshot(sh_base), self.snapshot(py_base))

    @staticmethod
    def edit(rel, text):
        def apply(base):
            path = os.path.join(base, "claude", rel)
            with open(path, "w") as handle:
                handle.write(text)
        return apply

    def test_fresh_then_repeat_then_check(self):
        self.scenario([[], [], ["--check"]])

    def test_dry_run_and_check_before_install(self):
        self.scenario([["--dry-run"], ["--check"]])

    def test_drift_backup_and_reinstall(self):
        self.scenario([[], self.edit("CLAUDE.md", "local\n"), ["--check"], ["--dry-run"], []])

    def test_no_link_bin(self):
        self.scenario([["--no-link-bin"], ["--check"]])

    def test_refusals(self):
        self.scenario([["--bogus"], ["-h"]])


if __name__ == "__main__":
    unittest.main()
