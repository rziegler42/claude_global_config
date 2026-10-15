#!/usr/bin/env python3
"""Validate and merge Claude semantic chunks into Graphify extraction JSON."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
import subprocess
from datetime import datetime, timezone


def ensure_graphify_runtime():
    """Re-exec with Graphify's adjacent Python when normal Python cannot import it."""
    if importlib.util.find_spec("graphify") is not None:
        return
    executable = shutil.which("graphify")
    if executable:
        python = Path(executable).resolve().parent / "python"
        if python.is_file() and os.environ.get("GRAPHIFY_CLAUDE_REEXEC") != "1":
            os.environ["GRAPHIFY_CLAUDE_REEXEC"] = "1"
            os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit("Graphify runtime not found; install graphifyy with uv and ensure graphify is on PATH")


ensure_graphify_runtime()

from graphify.cache import save_semantic_cache
from graphify.build import build_from_json
from graphify.cluster import cluster, label_communities_by_hub, score_all
from graphify.export import to_html, to_json

EMPTY = {"nodes": [], "edges": [], "hyperedges": []}
ID = re.compile(r"^[a-z0-9_]+$")
FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept"}
SCORES = {"EXTRACTED": {1.0}, "INFERRED": {0.95, 0.85, 0.75, 0.65, 0.55}}
HTML_NODE_LIMIT = 5000


def atomic_write(path, text):
    """Write text through a temporary file and os.replace, never through a symlink."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def whole_number(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10 ** 12


def safe_text(value, limit=200):
    return isinstance(value, str) and 0 < len(value.strip()) and len(value) <= limit and not any(
        ord(ch) < 32 or ord(ch) == 127 for ch in value)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def graph_counts(path):
    """Return prior serialized graph totals when a previous graph is available."""
    try:
        data = load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    nodes = data.get("nodes", [])
    edges = data.get("edges", data.get("links", []))
    hyperedges = data.get("hyperedges", [])
    if not all(isinstance(item, list) for item in (nodes, edges, hyperedges)):
        return None
    communities = {
        node.get("community") for node in nodes
        if isinstance(node, dict) and node.get("community") is not None
    }
    return {
        "nodes": len(nodes), "edges": len(edges), "hyperedges": len(hyperedges),
        "communities": len(communities),
    }


def graph_delta(before, after):
    if before is None:
        return None
    return {
        "before": before,
        "after": after,
        "delta": {key: after[key] - before.get(key, 0) for key in after},
    }


def valid(data, allowed, expected_sources):
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list) for k in EMPTY):
        return False
    for counter in ("input_tokens", "output_tokens"):
        if counter in data and not whole_number(data[counter]):
            return False
    coverage = data.get("coverage")
    if not isinstance(coverage, list) or len(coverage) != len(expected_sources):
        return False
    receipts = {}
    for item in coverage:
        if not isinstance(item, dict) or item.get("status") != "read_complete":
            return False
        source = item.get("source_file")
        if source in receipts or source not in expected_sources:
            return False
        if item.get("sha256") != expected_sources[source]["sha256"]:
            return False
        receipts[source] = item
    if set(receipts) != set(expected_sources):
        return False
    for source, record in expected_sources.items():
        path = Path(source)
        if not path.is_file() or path.stat().st_size != record["size_bytes"]:
            return False
        if file_sha256(path) != record["sha256"]:
            return False
    node_ids = set()
    for node in data["nodes"]:
        if (not isinstance(node, dict) or not ID.fullmatch(str(node.get("id", "")))
                or not safe_text(node.get("label")) or node.get("file_type") not in FILE_TYPES
                or node.get("source_file") not in allowed):
            return False
        node_ids.add(node["id"])
    for edge in data["edges"]:
        if not isinstance(edge, dict):
            return False
        confidence, score = edge.get("confidence"), edge.get("confidence_score")
        if (edge.get("source_file") not in allowed
                or not safe_text(edge.get("relation"))
                or not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str)
                or not edge.get("source") or not edge.get("target")
                or confidence not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
                or not isinstance(score, (int, float))
                or (confidence in SCORES and score not in SCORES[confidence])
                or (confidence == "AMBIGUOUS" and not 0.1 <= score <= 0.3)):
            return False
    for hyperedge in data["hyperedges"]:
        if (not isinstance(hyperedge, dict) or hyperedge.get("source_file") not in allowed
                or not safe_text(hyperedge.get("relation"))
                or not isinstance(hyperedge.get("nodes"), list)
                or not all(isinstance(item, str) for item in hyperedge.get("nodes", []))
                or len(hyperedge.get("nodes", [])) < 3):
            return False
    return True


def merge(parts):
    result = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for part in parts:
        for key in EMPTY:
            result[key].extend(part.get(key, []))
        result["input_tokens"] += int(part.get("input_tokens", 0))
        result["output_tokens"] += int(part.get("output_tokens", 0))
    result["nodes"] = list({n["id"]: n for n in result["nodes"]}.values())
    result["edges"] = list({(e.get("source"), e.get("target"), e.get("relation"), e.get("source_file")): e for e in result["edges"]}.values())
    result["hyperedges"] = list({(tuple(h.get("nodes", [])), h.get("relation"), h.get("source_file")): h for h in result["hyperedges"]}.values())
    return result


def validate_semantic_endpoints(data, external_ids=()):
    identifiers = {node["id"] for node in data["nodes"]}.union(external_ids)
    dangling = [edge for edge in data["edges"] if edge.get("source") not in identifiers or edge.get("target") not in identifiers]
    dangling_hyper = [edge for edge in data["hyperedges"] if any(node not in identifiers for node in edge.get("nodes", []))]
    if dangling or dangling_hyper:
        raise ValueError(f"dangling semantic endpoints: {len(dangling)} edges, {len(dangling_hyper)} hyperedges")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--out", default="graphify-out")
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.project_root.resolve(), (args.project_root.resolve() / args.out)
    previous_counts = graph_counts(out / "graph.json")
    manifest = load(out / ".graphify_chunks.json")
    refresh_head = None
    try:
        recorded = load(out / ".claude_refresh.json")
        if (isinstance(recorded, dict) and isinstance(recorded.get("head"), str)
                and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", recorded["head"])):
            refresh_head = recorded["head"]
    except (OSError, ValueError):
        pass
    good, failed, sources, seen_files = [], [], [], set()
    for chunk in manifest["chunks"]:
        try:
            path, allowed = Path(chunk["output"]), set(chunk["files"])
            if allowed & seen_files:
                raise ValueError("a source file is assigned to more than one chunk")
            seen_files.update(allowed)
            if not re.fullmatch(r"graphify-out/\.graphify_chunk_[0-9]+\.json", Path(chunk["output"]).as_posix()):
                raise ValueError("chunk output path is outside graphify-out")
            for source in allowed:
                resolved = Path(source).resolve()
                if not Path(source).is_absolute() or root not in resolved.parents or Path(source).is_symlink():
                    raise ValueError("chunk source is not a regular file under the project")
            path = root / path
            data = load(path)
            expected_sources = {item["source_file"]: item for item in chunk.get("sources", [])}
            if set(expected_sources) != allowed:
                raise ValueError("prepared source metadata")
            if not valid(data, allowed, expected_sources):
                raise ValueError("schema, source scope, or coverage")
            good.append(data)
            sources.extend(chunk["files"])
        except (OSError, ValueError, TypeError, AttributeError, KeyError, OverflowError,
                RecursionError, json.JSONDecodeError) as exc:
            failed.append({"chunk": chunk.get("number") if isinstance(chunk, dict) else None,
                           "error": str(exc)[:200]})
    if failed:
        raise SystemExit(
            f"refusing merge: {len(failed)} of {len(manifest['chunks'])} chunks failed: {failed}"
        )
    try:
        fresh = merge(good)
        ast = load(out / ".graphify_ast.json")
        cached = load(out / ".graphify_cached.json")
        ast_ids = {node["id"] for node in ast["nodes"]}
        for part in (cached, fresh):
            for node in part["nodes"]:
                if node["id"] in ast_ids:
                    raise ValueError("a semantic node reuses a code node id")
        semantic = merge([cached, fresh])
        validate_semantic_endpoints(semantic, ast_ids)
        combined = merge([ast, semantic])
    except (OSError, ValueError, TypeError, AttributeError, KeyError, OverflowError,
            RecursionError, json.JSONDecodeError) as exc:
        raise SystemExit(f"refusing merge: merged data is not valid: {str(exc)[:200]}")
    graph = build_from_json(combined, directed=True, root=root)
    communities = cluster(graph)
    labels = label_communities_by_hub(graph, communities)
    cohesion = score_all(graph, communities)
    current_counts = {
        "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
        "hyperedges": len(combined["hyperedges"]), "communities": len(communities),
    }
    delta = graph_delta(previous_counts, current_counts)
    analysis = {"communities": {str(k): v for k, v in communities.items()}, "cohesion": {str(k): v for k, v in cohesion.items()}}
    report = f"# Graphify report\n\n- Nodes: {graph.number_of_nodes()}\n- Edges: {graph.number_of_edges()}\n- Communities: {len(communities)}\n- Failed semantic chunks: {len(failed)}\n"
    if delta:
        changes = ", ".join(f"{name} {amount:+d}" for name, amount in delta["delta"].items())
        report += f"- Change since prior graph: {changes}\n"
    visualization = {
        "generated": False,
        "mode": "community" if graph.number_of_nodes() > HTML_NODE_LIMIT else "full",
        "node_limit": HTML_NODE_LIMIT,
        "warning": None,
    }
    with tempfile.TemporaryDirectory(dir=out) as temp_name:
        temp = Path(temp_name)
        payloads = {
            ".graphify_semantic_new.json": fresh,
            ".graphify_extraction.json": combined,
            ".graphify_failures.json": failed,
            ".graphify_analysis.json": analysis,
            ".graphify_labels.json": {str(k): v for k, v in labels.items()},
        }
        for name, value in payloads.items():
            (temp / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        to_json(graph, communities, str(temp / "graph.json"), force=True, community_labels=labels)
        try:
            rendered = to_html(
                graph, communities, str(temp / "graph.html"),
                community_labels=labels, node_limit=HTML_NODE_LIMIT,
            )
            if not rendered or not (temp / "graph.html").is_file():
                raise RuntimeError("Graphify HTML exporter produced no viewer")
            visualization["generated"] = True
        except Exception as exc:
            visualization["warning"] = str(exc)
        report += (
            f"- Visualization: {visualization['mode']} "
            f"({'generated' if visualization['generated'] else 'unavailable'})\n"
        )
        if visualization["warning"]:
            report += f"- Visualization warning: {visualization['warning']}\n"
        (temp / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
        (temp / ".claude_graph_visualization.json").write_text(
            json.dumps(visualization, indent=2), encoding="utf-8",
        )
        for path in temp.iterdir():
            os.replace(path, out / path.name)
    if not visualization["generated"]:
        (out / "graph.html").unlink(missing_ok=True)
    if sources:
        save_semantic_cache(fresh["nodes"], fresh["edges"], fresh["hyperedges"], root=root, merge_existing=True, allowed_source_files=sources, prompt_file=args.spec.resolve())
    version = manifest.get("graphify_version")
    head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False)
    head_value = head_result.stdout.strip() if head_result.returncode == 0 else None
    # The refresh covered the tree as it was at prepare time; commits made since
    # are not ingested and must keep the graph stale.
    ingested_head = refresh_head  # None when prepare's head is unknown: no semantic baseline
    state = {
        "head": head_value,
        "semantic_head": ingested_head,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graphify_version": version,
    }
    atomic_write(out / ".claude_graph_state.json", json.dumps(state, indent=2))
    (out / ".claude_refresh.json").unlink(missing_ok=True)
    print(json.dumps({"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "hyperedges": len(combined["hyperedges"]), "communities": len(communities), "graph_delta": delta, "failed_chunks": failed, "visualization": visualization}))


if __name__ == "__main__":
    main()
