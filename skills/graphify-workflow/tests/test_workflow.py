"""Regression tests for the Graphify workflow helper and scripts.

Run from anywhere with:  python3 -m unittest discover -s <skill>/tests
Uses throwaway Git repositories and a stub `graphify`; nothing outside the
temporary directories is touched.
"""
import ast
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

sys.dont_write_bytecode = True  # do not leave __pycache__ in the skill directory

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
HELPER = Path(__file__).resolve().parents[3] / "bin" / "claude-workflow"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


CW = load("claude_workflow", HELPER)
POST = load("graphify_post_commit", SCRIPTS / "post_commit.py")


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True).stdout


class Repo:
    """A throwaway repository with a graph whose state file records HEAD."""

    def __init__(self, stub_exit=0):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        stub = self.bin / "graphify"
        stub.write_text(f"#!/bin/sh\nexit {stub_exit}\n")
        stub.chmod(0o755)
        real = shutil.which("graphify")
        if real:
            # The workflow scripts look for Graphify's Python next to the `graphify` on PATH.
            python = self.bin / "python"
            python.write_text(f'#!/bin/sh\nexec "{Path(real).resolve().parent / "python"}" "$@"\n')
            python.chmod(0o755)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        self.write("a.py", "x = 1\n")
        self.commit("c0")
        out = self.root / "graphify-out"
        out.mkdir()
        (out / "graph.json").write_text('{"nodes":[],"edges":[]}')
        self.set_state(head=self.head())

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message):
        git(self.root, "add", "-A", "--", ".", ":!graphify-out")
        git(self.root, "commit", "-q", "-m", message)

    def head(self):
        return git(self.root, "rev-parse", "HEAD").strip()

    def set_state(self, **state):
        (self.root / "graphify-out" / ".claude_graph_state.json").write_text(json.dumps(state))

    def status(self):
        return CW.graph_status_details(self.root)["status"]

    def post_commit(self):
        env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        out = subprocess.run([sys.executable, "-B", str(SCRIPTS / "post_commit.py"), str(self.root)],
                             env=env, check=True, text=True, capture_output=True).stdout
        return json.loads(out.strip().splitlines()[-1])

    def cleanup(self):
        self.tmp.cleanup()


class StatusAndPostCommit(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def test_current_at_recorded_head(self):
        self.assertEqual(self.repo.status(), "current")

    def test_code_only_commit_does_not_hide_pending_semantic_changes(self):
        repo = self.repo
        repo.write("doc.md", "# doc\n")
        repo.commit("docs")
        self.assertEqual(repo.post_commit()["graphify_post_commit"], "semantic_refresh_required")
        self.assertEqual(repo.status(), "stale_semantic")
        repo.write("a.py", "x = 2\n")
        repo.commit("code")
        self.assertEqual(repo.post_commit()["graphify_post_commit"], "updated")
        self.assertEqual(repo.status(), "stale_semantic")

    def test_semantic_head_after_finalize_makes_graph_current(self):
        repo = self.repo
        repo.write("doc.md", "# doc\n")
        repo.commit("docs")
        repo.post_commit()
        repo.set_state(head=repo.head(), semantic_head=repo.head())
        self.assertEqual(repo.status(), "current")

    def test_legacy_state_without_semantic_head_still_works(self):
        repo = self.repo
        repo.write("doc.md", "# doc\n")
        repo.commit("docs")
        self.assertEqual(repo.status(), "stale_semantic")

    def test_post_commit_is_idempotent_for_one_commit(self):
        repo = self.repo
        repo.write("b.py", "y = 1\n")
        repo.commit("code")
        self.assertEqual(repo.post_commit()["graphify_post_commit"], "updated")
        self.assertEqual(repo.post_commit()["graphify_post_commit"], "already_processed")

    def test_unresolvable_semantic_head_is_never_current(self):
        self.repo.set_state(head=self.repo.head(), semantic_head="0" * 40)
        self.assertEqual(self.repo.status(), "present")

    def test_unresolvable_recorded_head_is_never_current(self):
        self.repo.set_state(head="0" * 40)
        self.assertEqual(self.repo.status(), "present")

    def test_uppercase_extension_counts_as_semantic(self):
        repo = self.repo
        repo.write("README.MD", "# doc\n")
        repo.commit("upper")
        self.assertEqual(repo.post_commit()["graphify_post_commit"], "semantic_refresh_required")


@unittest.skipUnless(shutil.which("graphify"), "needs the Graphify runtime for its ignore rules")
class IgnoredPathsDoNotMakeTheGraphStale(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write(".graphifyignore", "/docs/plans/next.md\n")
        self.repo.commit("ignore rules")
        self.repo.set_state(head=self.repo.head(), semantic_head=self.repo.head())

    def test_dirty_ignored_file_leaves_the_graph_current(self):
        self.repo.write("docs/plans/next.md", "# plan\n")
        self.assertEqual(self.repo.status(), "current")

    def test_dirty_unignored_document_still_makes_it_stale(self):
        self.repo.write("docs/plans/other.md", "# plan\n")
        self.assertEqual(self.repo.status(), "stale_semantic")

    def test_committed_ignored_file_leaves_the_graph_current_after_post_commit(self):
        self.repo.write("docs/plans/next.md", "# plan\n")
        self.repo.commit("plan")
        self.assertEqual(self.repo.post_commit()["graphify_post_commit"], "updated")
        self.assertEqual(self.repo.status(), "current")

    def test_committed_unignored_document_still_requests_a_semantic_refresh(self):
        self.repo.write("docs/plans/other.md", "# plan\n")
        self.repo.commit("plan")
        self.assertEqual(self.repo.post_commit()["graphify_post_commit"], "semantic_refresh_required")

    def test_unavailable_ignore_helper_falls_back_to_stale(self):
        self.repo.write("docs/plans/next.md", "# plan\n")
        with unittest.mock.patch.object(CW.subprocess, "run", side_effect=OSError("no helper")):
            self.assertEqual(CW.graph_ignored_paths(self.repo.root, {"docs/plans/next.md"}), set())


class PostCommitRetries(unittest.TestCase):
    def test_failed_update_retries_once_then_is_exhausted(self):
        repo = Repo(stub_exit=1)
        self.addCleanup(repo.cleanup)
        repo.write("b.py", "y = 1\n")
        repo.commit("code")
        first = repo.post_commit()
        self.assertEqual((first["graphify_post_commit"], first["attempts"]), ("failed", 1))
        second = repo.post_commit()
        self.assertEqual((second["graphify_post_commit"], second["attempts"]), ("failed", 2))
        self.assertEqual(repo.post_commit()["graphify_post_commit"], "retry_exhausted")


class DoctorStates(unittest.TestCase):
    """graph-doctor reports one state and one safe next action, without mutating."""

    def doctor(self, repo):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            CW.graph_doctor(repo.root)
        return json.loads(buffer.getvalue().strip().splitlines()[-1])

    def prepared(self, chunks_written, chunks_total=2, manifest=True):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        out = repo.root / "graphify-out"
        (out / ".claude_refresh.json").write_text(json.dumps({"status": "prepared"}))
        outputs = [f"graphify-out/.graphify_chunk_{n:02d}.json" for n in range(1, chunks_total + 1)]
        if manifest:
            (out / ".graphify_chunks.json").write_text(json.dumps(
                {"chunks": [{"output": path} for path in outputs]}))
        for path in outputs[:chunks_written]:
            (repo.root / path).write_text("{}")
        return repo

    def test_prepared_states_and_next_actions(self):
        cases = [
            (self.prepared(0), "prepared_no_chunks", "graph-abort --confirm"),
            (self.prepared(1), "prepared_partial_chunks", "do not use graph-abort"),
            (self.prepared(2), "prepared_all_chunks_written", "graph-finalize"),
            (self.prepared(0, manifest=False), "prepared_manifest_missing", "graph-abort --confirm"),
        ]
        for repo, status, action in cases:
            result = self.doctor(repo)
            self.assertEqual(result["status"], status)
            self.assertIn(action, result["next_action"])

    def test_missing_graph_points_at_prepare(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        shutil.rmtree(repo.root / "graphify-out")
        (repo.root / "graphify-out").mkdir()
        result = self.doctor(repo)
        self.assertEqual(result["status"], "graph_missing")
        self.assertIn("graph-prepare", result["next_action"])

    def test_doctor_does_not_mutate_state(self):
        repo = self.prepared(1)
        before = sorted(p.name for p in (repo.root / "graphify-out").iterdir())
        self.doctor(repo)
        self.assertEqual(before, sorted(p.name for p in (repo.root / "graphify-out").iterdir()))


class DirtyPaths(unittest.TestCase):
    def test_rename_lists_both_real_paths(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        git(repo.root, "mv", "a.py", "renamed_module.py")
        paths = CW.dirty_paths(repo.root)
        self.assertEqual(paths, {"a.py", "renamed_module.py"})


class Abort(unittest.TestCase):
    def test_abort_clears_marker_when_manifest_is_missing(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        marker = repo.root / "graphify-out" / ".claude_refresh.json"
        marker.write_text(json.dumps({"status": "prepared"}))
        CW.graph_abort(repo.root, True)
        self.assertFalse(marker.exists())

    def test_abort_still_refuses_when_a_chunk_exists(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        out = repo.root / "graphify-out"
        (out / ".claude_refresh.json").write_text(json.dumps({"status": "prepared"}))
        (out / ".graphify_chunks.json").write_text(json.dumps(
            {"chunks": [{"output": "graphify-out/.graphify_chunk_01.json"}]}))
        (out / ".graphify_chunk_01.json").write_text("{}")
        with self.assertRaises(RuntimeError):
            CW.graph_abort(repo.root, True)


class FinalizeValidator(unittest.TestCase):
    """Load valid() from finalize.py without importing Graphify."""

    @classmethod
    def setUpClass(cls):
        tree = ast.parse((SCRIPTS / "finalize.py").read_text())
        cls.ns = {
            "hashlib": hashlib, "re": re, "Path": Path,
            "EMPTY": {"nodes": [], "edges": [], "hyperedges": []},
            "ID": re.compile(r"^[a-z0-9_]+$"),
            "FILE_TYPES": {"code", "document", "paper", "image", "rationale", "concept"},
            "SCORES": {"EXTRACTED": {1.0}, "INFERRED": {0.95, 0.85, 0.75, 0.65, 0.55}},
        }
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in {"valid", "file_sha256"}:
                exec(compile(ast.Module([node], []), "finalize.py", "exec"), cls.ns)

    def test_non_dict_edge_is_rejected_not_a_crash(self):
        data = {"coverage": [], "nodes": [], "edges": ["not-a-dict"], "hyperedges": []}
        self.assertFalse(self.ns["valid"](data, set(), {}))

    def test_non_list_hyperedge_nodes_are_rejected(self):
        data = {"coverage": [], "nodes": [], "edges": [],
                "hyperedges": [{"source_file": "x", "relation": "r", "nodes": 5}]}
        self.assertFalse(self.ns["valid"](data, {"x"}, {}))

    def test_finalize_writes_semantic_head(self):
        self.assertIn('"semantic_head"', (SCRIPTS / "finalize.py").read_text())


@unittest.skipUnless(shutil.which("graphify"), "graphify executable not available")
class EndToEndRefresh(unittest.TestCase):
    """prepare -> hand-built chunk -> validate -> finalize -> status, without an LLM."""

    def run_helper(self, root, *args):
        result = subprocess.run([sys.executable, str(HELPER), *args], cwd=root,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, f"{args}: {result.stdout[-300:]} {result.stderr[-300:]}")
        return result.stdout.strip()

    def test_full_refresh_makes_graph_current_and_tracks_semantic_head(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        shutil.rmtree(repo.root / "graphify-out")  # start with no graph
        repo.write("README.md", "# Title\n\nText about a.\n")
        repo.commit("docs")
        out = repo.root / "graphify-out"

        prepared = json.loads(self.run_helper(repo.root, "graph-prepare").splitlines()[-1])
        self.assertGreaterEqual(prepared["chunks"], 1)
        self.assertTrue((out / ".graphify_chunks.json").is_file())
        self.assertTrue((out / ".claude_refresh.json").is_file())  # marker follows the manifest

        manifest = json.loads((out / ".graphify_chunks.json").read_text())
        for chunk in manifest["chunks"]:
            data = {
                "coverage": [{"source_file": s["source_file"], "sha256": s["sha256"],
                              "status": "read_complete"} for s in chunk["sources"]],
                "nodes": [{"id": "chunk_%02d_node" % chunk["number"], "label": "Node",
                           "file_type": "document", "source_file": chunk["files"][0]}],
                "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0,
            }
            (repo.root / chunk["output"]).write_text(json.dumps(data))
            self.assertIn('"valid"', self.run_helper(repo.root, "graph-validate-chunk", chunk["output"]))

        self.run_helper(repo.root, "graph-finalize")
        self.assertFalse((out / ".claude_refresh.json").exists())
        state = json.loads((out / ".claude_graph_state.json").read_text())
        self.assertEqual(state["head"], repo.head())
        self.assertEqual(state["semantic_head"], repo.head())
        self.assertEqual(repo.status(), "current")

        repo.write("later.md", "# Later\n")
        repo.commit("later docs")
        self.assertEqual(repo.status(), "stale_semantic")

    def test_second_prepare_refuses_and_keeps_written_chunks(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        shutil.rmtree(repo.root / "graphify-out")
        repo.write("README.md", "# Title\n\nText.\n")
        repo.commit("docs")
        self.run_helper(repo.root, "graph-prepare")
        chunk = repo.root / "graphify-out" / ".graphify_chunk_01.json"
        chunk.write_text('{"worker": "output already written"}')
        again = subprocess.run([sys.executable, "-B", str(HELPER), "graph-prepare"], cwd=repo.root,
                               text=True, capture_output=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("already in progress", again.stdout)
        self.assertTrue(chunk.is_file())

    def test_prepare_after_abort_is_allowed(self):
        repo = Repo()
        self.addCleanup(repo.cleanup)
        shutil.rmtree(repo.root / "graphify-out")
        repo.write("README.md", "# Title\n\nText.\n")
        repo.commit("docs")
        self.run_helper(repo.root, "graph-prepare")
        self.run_helper(repo.root, "graph-abort", "--confirm")
        self.run_helper(repo.root, "graph-prepare")


class Consistency(unittest.TestCase):
    def test_semantic_extension_sets_match(self):
        self.assertEqual(CW.SEMANTIC_EXTENSIONS, POST.SEMANTIC_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
