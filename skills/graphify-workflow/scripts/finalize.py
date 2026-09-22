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


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


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
    nodes = data.get("nodes", [])
    edges = data.get("edges", data.get("links", []))
    hyperedges = data.get("hyperedges", [])
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
                or not str(node.get("label", "")).strip() or node.get("file_type") not in FILE_TYPES
                or node.get("source_file") not in allowed):
            return False
        node_ids.add(node["id"])
    for edge in data["edges"]:
        confidence, score = edge.get("confidence"), edge.get("confidence_score")
        if (not isinstance(edge, dict) or edge.get("source_file") not in allowed
                or not str(edge.get("relation", "")).strip() or not edge.get("source") or not edge.get("target")
                or confidence not in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
                or not isinstance(score, (int, float))
                or (confidence in SCORES and score not in SCORES[confidence])
                or (confidence == "AMBIGUOUS" and not 0.1 <= score <= 0.3)):
            return False
    for hyperedge in data["hyperedges"]:
        if (not isinstance(hyperedge, dict) or hyperedge.get("source_file") not in allowed
                or not str(hyperedge.get("relation", "")).strip()
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
    good, failed, sources = [], [], []
    for chunk in manifest["chunks"]:
        path, allowed = Path(chunk["output"]), set(chunk["files"])
        try:
            data = load(path)
            expected_sources = {item["source_file"]: item for item in chunk.get("sources", [])}
            if set(expected_sources) != allowed:
                raise ValueError("prepared source metadata")
            if not valid(data, allowed, expected_sources):
                raise ValueError("schema, source scope, or coverage")
            good.append(data)
            sources.extend(chunk["files"])
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            failed.append({"chunk": chunk["number"], "error": str(exc)})
    if failed:
        raise SystemExit(
            f"refusing merge: {len(failed)} of {len(manifest['chunks'])} chunks failed: {failed}"
        )
    fresh = merge(good)
    ast = load(out / ".graphify_ast.json")
    cached = load(out / ".graphify_cached.json")
    semantic = merge([cached, fresh])
    validate_semantic_endpoints(semantic, {node["id"] for node in ast["nodes"]})
    combined = merge([ast, semantic])
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
    state = {
        "head": head_result.stdout.strip() if head_result.returncode == 0 else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "graphify_version": version,
    }
    (out / ".claude_graph_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    (out / ".claude_refresh.json").unlink(missing_ok=True)
    print(json.dumps({"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "hyperedges": len(combined["hyperedges"]), "communities": len(communities), "graph_delta": delta, "failed_chunks": failed, "visualization": visualization}))


if __name__ == "__main__":
    main()
