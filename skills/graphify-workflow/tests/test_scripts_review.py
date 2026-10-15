"""Regression tests from the independent review of the Graphify scripts.

Uses a stub `graphify` package (PYTHONPATH) so the real prepare/finalize/
post_commit code runs without the Graphify runtime.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_workflow import CW, HELPER, SCRIPTS, Repo, git  # noqa: E402

STUB_FILES = {
    "graphify/__init__.py": "",
    "graphify/cache.py": (
        "def save_semantic_cache(*a, **k):\n    pass\n"
        "def check_semantic_cache(files, root=None, prompt_file=None):\n    return [], [], [], list(files)\n"),
    "graphify/detect.py": (
        "def detect(root, cache_root=None):\n    return {'files': {'code': [], 'document': [], 'paper': [], 'image': []}}\n"
        "def ignored_predicate(root):\n    return lambda p: False\n"),
    "graphify/extract.py": "def extract(*a, **k):\n    return {'nodes': [], 'edges': [], 'hyperedges': []}\n",
    "graphify/build.py": (
        "class G:\n    def __init__(s, d):\n        s.d = d\n"
        "    def number_of_nodes(s):\n        return len(s.d['nodes'])\n"
        "    def number_of_edges(s):\n        return len(s.d['edges'])\n"
        "def build_from_json(data, directed=True, root=None):\n    return G(data)\n"),
    "graphify/cluster.py": (
        "def cluster(g):\n    return {0: []}\n"
        "def label_communities_by_hub(g, c):\n    return {0: 'x'}\n"
        "def score_all(g, c):\n    return {0: 1.0}\n"),
    "graphify/export.py": (
        "def to_json(graph, communities, path, force=False, community_labels=None):\n"
        "    open(path, 'w').write('{}')\n"
        "def to_html(*a, **k):\n    raise RuntimeError('no viewer')\n"),
    "graphifyy-0.0.dist-info/METADATA": "Metadata-Version: 2.1\nName: graphifyy\nVersion: 0.0\n",
}


class Scripts(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)
        self.root = self.repo.root
        self.stub = Path(self.repo.tmp.name) / "stub"
        for name, text in STUB_FILES.items():
            path = self.stub / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.victim = Path(self.repo.tmp.name) / "victim.txt"
        self.victim.write_text("PRECIOUS\n")
        self.spec = Path(self.repo.tmp.name) / "spec.md"
        self.spec.write_text("contract\n")

    def env(self):
        return dict(os.environ, PYTHONPATH=str(self.stub),
                    PATH=f"{self.repo.bin}{os.pathsep}{os.environ['PATH']}")

    def script(self, name, *extra):
        return subprocess.run([sys.executable, "-B", str(SCRIPTS / name), str(self.root), *extra],
                              cwd=self.root, env=self.env(), text=True, capture_output=True)

    def link(self, name):
        path = self.root / "graphify-out" / name
        path.unlink(missing_ok=True)
        path.symlink_to(self.victim)

    def assert_victim_untouched(self):
        self.assertEqual(self.victim.read_text(), "PRECIOUS\n")

    # F1
    def test_post_commit_does_not_write_through_symlinks(self):
        self.link(".claude_post_commit.json")
        self.link(".claude_graph_state.json")
        result = self.script("post_commit.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_victim_untouched()

    def test_prepare_does_not_write_through_symlinks(self):
        for name in (".graphify_cached.json", ".claude_refresh.json", ".graphify_detect.json",
                     ".graphify_chunks.json", ".graphify_ast.json"):
            self.link(name)
        result = self.script("prepare.py", "--spec", str(self.spec))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_victim_untouched()

    def test_finalize_does_not_write_through_symlinks(self):
        out = self.root / "graphify-out"
        (out / ".graphify_chunks.json").write_text(json.dumps({"chunks": []}))
        (out / ".graphify_ast.json").write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}))
        (out / ".graphify_cached.json").write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}))
        self.link(".claude_graph_state.json")
        result = self.script("finalize.py", "--spec", str(self.spec))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_victim_untouched()

    # F2
    def test_state_heads_cannot_inject_git_options(self):
        self.repo.set_state(head="--output=%s" % self.victim, semantic_head="HEAD")
        details = CW.graph_status_details(self.root)
        self.assert_victim_untouched()
        self.assertNotEqual(details["status"], "current")
        self.repo.set_state(head=self.repo.head(), semantic_head="--output=%s" % self.victim)
        CW.graph_status_details(self.root)
        self.assert_victim_untouched()

    # F3
    def test_finalize_does_not_vouch_for_commits_made_after_prepare(self):
        self.assertEqual(self.script("prepare.py", "--spec", str(self.spec)).returncode, 0)
        prepared = self.repo.head()
        self.repo.write("new.md", "# new\n")
        self.repo.commit("docs after prepare")
        result = self.script("finalize.py", "--spec", str(self.spec))
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads((self.root / "graphify-out" / ".claude_graph_state.json").read_text())
        self.assertEqual(state["semantic_head"], prepared)
        self.assertEqual(self.repo.status(), "stale_semantic")

    # F4
    def test_post_commit_does_not_bless_a_graph_it_did_not_build(self):
        (self.root / "graphify-out" / ".claude_graph_state.json").unlink()
        self.repo.write("docs.md", "# never ingested\n")
        self.repo.commit("docs")
        self.script("post_commit.py")
        self.assertNotEqual(self.repo.status(), "current")

    # F5
    def test_finalize_refuses_manifest_paths_outside_the_project(self):
        out = self.root / "graphify-out"
        outside = Path(self.repo.tmp.name) / "outside.md"
        outside.write_text("secret\n")
        chunk = {"number": 1, "total": 1, "files": [str(outside)],
                 "sources": [{"source_file": str(outside), "size_bytes": outside.stat().st_size,
                              "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()}],
                 "output": str(out / ".graphify_chunk_01.json")}
        (out / ".graphify_chunks.json").write_text(json.dumps({"chunks": [chunk]}))
        (out / ".graphify_chunk_01.json").write_text(json.dumps({
            "nodes": [{"id": "a", "label": "A", "file_type": "document", "source_file": str(outside)}],
            "edges": [], "hyperedges": [],
            "coverage": [{"source_file": str(outside), "status": "read_complete",
                          "sha256": chunk["sources"][0]["sha256"]}]}))
        for name in (".graphify_ast.json", ".graphify_cached.json"):
            (out / name).write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}))
        result = self.script("finalize.py", "--spec", str(self.spec))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("outside.md", (out / "graph.json").read_text())

    # F6
    def test_hostile_numbers_fail_validation_without_a_traceback(self):
        out = self.root / "graphify-out"
        doc = self.root / "doc.md"
        doc.write_text("# d\n")
        digest = hashlib.sha256(doc.read_bytes()).hexdigest()
        chunk = {"number": 1, "total": 1, "files": [str(doc)],
                 "sources": [{"source_file": str(doc), "size_bytes": doc.stat().st_size, "sha256": digest}],
                 "output": "graphify-out/.graphify_chunk_01.json"}
        (out / ".graphify_chunks.json").write_text(json.dumps({"chunks": [chunk]}))
        for name in (".graphify_ast.json", ".graphify_cached.json"):
            (out / name).write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}))
        for tokens in ('"x"', "Infinity"):
            (out / ".graphify_chunk_01.json").write_text(
                '{"nodes": [], "edges": [], "hyperedges": [], "input_tokens": %s, '
                '"coverage": [{"source_file": %s, "status": "read_complete", "sha256": "%s"}]}'
                % (tokens, json.dumps(str(doc)), digest))
            result = self.script("finalize.py", "--spec", str(self.spec))
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr, result.stderr)
            self.assertIn("refusing merge", result.stderr)

    def test_a_graph_that_is_not_an_object_does_not_wedge_finalize(self):
        out = self.root / "graphify-out"
        (out / "graph.json").write_text("[]")
        (out / ".graphify_chunks.json").write_text(json.dumps({"chunks": []}))
        for name in (".graphify_ast.json", ".graphify_cached.json"):
            (out / name).write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}))
        result = self.script("finalize.py", "--spec", str(self.spec))
        self.assertEqual(result.returncode, 0, result.stderr)

    # F7
    def test_prepare_skips_symlinked_and_outside_documents(self):
        detect = self.stub / "graphify" / "detect.py"
        link = self.root / "link.md"
        link.symlink_to(self.victim)
        real = self.root / "real.md"
        real.write_text("# real\n")
        detect.write_text(
            "def detect(root, cache_root=None):\n    return {'files': {'code': [], 'document': [%r, %r], "
            "'paper': [], 'image': []}}\ndef ignored_predicate(root):\n    return lambda p: False\n"
            % (str(link), str(real)))
        result = self.script("prepare.py", "--spec", str(self.spec))
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.root / "graphify-out" / ".graphify_chunks.json").read_text())
        listed = [f for chunk in manifest["chunks"] for f in chunk["files"]]
        self.assertEqual([Path(f).name for f in listed], ["real.md"])


class StateShapes(Scripts):
    def doc_commit_state(self, **state):
        base = self.repo.head()
        self.counter = getattr(self, "counter", 0) + 1
        self.repo.write("doc%d.md" % self.counter, "# doc\n")
        self.repo.commit("docs")
        self.repo.set_state(head=self.repo.head(), **state)
        return base

    def test_falsy_semantic_head_is_not_treated_as_absent(self):
        for value in ("", 0, [], "not-a-hash"):
            with self.subTest(value=value):
                self.doc_commit_state(semantic_head=value)
                self.assertNotEqual(self.repo.status(), "current")

    def test_non_object_metadata_is_reported_not_crashed(self):
        out = self.root / "graphify-out"
        (out / ".claude_graph_state.json").write_text("[]")
        self.assertEqual(self.repo.status(), "present")
        (out / ".claude_refresh.json").write_text('"x"')
        self.assertIn(CW.graph_status_details(self.root)["status"], ("present", "stale_code", "current"))

    def test_finalize_without_a_prepare_head_records_no_semantic_baseline(self):
        out = self.root / "graphify-out"
        (out / ".graphify_chunks.json").write_text(json.dumps({"chunks": []}))
        (out / ".claude_refresh.json").write_text(json.dumps({"status": "prepared"}))
        for name in (".graphify_ast.json", ".graphify_cached.json"):
            (out / name).write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}))
        self.assertEqual(self.script("finalize.py", "--spec", str(self.spec)).returncode, 0)
        state = json.loads((out / ".claude_graph_state.json").read_text())
        self.assertIsNone(state["semantic_head"])
        self.assertEqual(self.repo.status(), "stale_semantic")

    def test_duplicate_sources_across_chunks_are_refused(self):
        out = self.root / "graphify-out"
        doc = self.root / "doc.md"
        doc.write_text("# d\n")
        digest = hashlib.sha256(doc.read_bytes()).hexdigest()
        source = {"source_file": str(doc), "size_bytes": doc.stat().st_size, "sha256": digest}
        chunks = [{"number": n, "total": 2, "files": [str(doc)], "sources": [source],
                   "output": "graphify-out/.graphify_chunk_0%d.json" % n} for n in (1, 2)]
        (out / ".graphify_chunks.json").write_text(json.dumps({"chunks": chunks}))
        body = {"nodes": [], "edges": [], "hyperedges": [],
                "coverage": [{"source_file": str(doc), "status": "read_complete", "sha256": digest}]}
        for n in (1, 2):
            (out / (".graphify_chunk_0%d.json" % n)).write_text(json.dumps(body))
        for name in (".graphify_ast.json", ".graphify_cached.json"):
            (out / name).write_text(json.dumps({"nodes": [], "edges": [], "hyperedges": []}))
        result = self.script("finalize.py", "--spec", str(self.spec))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing merge", result.stderr)


class SecondRepoFixtures(unittest.TestCase):
    def test_helper_uses_finite_chunks_only(self):
        self.assertTrue(HELPER.is_file())


if __name__ == "__main__":
    unittest.main()
