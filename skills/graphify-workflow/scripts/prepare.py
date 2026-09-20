#!/usr/bin/env python3
"""Prepare deterministic Graphify extraction and Claude semantic chunks."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
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

from graphify.cache import check_semantic_cache
from graphify.detect import detect
from graphify.extract import extract

EMPTY = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def source_record(path):
    source = Path(path)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "source_file": str(source),
        "size_bytes": source.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def chunk_sources(paths, max_files, max_bytes):
    groups, current, current_bytes = [], [], 0
    for path in paths:
        record = source_record(path)
        size = record["size_bytes"]
        if current and (len(current) >= max_files or current_bytes + size > max_bytes):
            groups.append(current)
            current, current_bytes = [], 0
        current.append(record)
        current_bytes += size
        if size >= max_bytes:
            groups.append(current)
            current, current_bytes = [], 0
    if current:
        groups.append(current)
    return groups


def prune_dangling_cached(ast, nodes, edges, hyperedges):
    identifiers = {node["id"] for node in ast.get("nodes", [])}.union(
        node["id"] for node in nodes
    )
    kept_edges = [
        edge for edge in edges
        if edge.get("source") in identifiers and edge.get("target") in identifiers
    ]
    kept_hyperedges = [
        edge for edge in hyperedges
        if all(node in identifiers for node in edge.get("nodes", []))
    ]
    return kept_edges, kept_hyperedges, len(edges) - len(kept_edges), len(hyperedges) - len(kept_hyperedges)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--out", default="graphify-out")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=22)
    parser.add_argument("--chunk-bytes", type=int, default=300_000)
    args = parser.parse_args()
    if args.chunk_size < 1 or args.chunk_bytes < 1:
        raise SystemExit("chunk-size and chunk-bytes must be positive")
    root = args.project_root.resolve()
    out = (root / args.out).resolve()
    spec = args.spec.resolve()
    contract = spec.read_text(encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / ".claude_refresh.json", {
        "status": "prepared",
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    version = importlib.metadata.version("graphifyy")
    detected = detect(root, cache_root=root)
    write_json(out / ".graphify_detect.json", detected)
    code = [Path(p) for p in detected.get("files", {}).get("code", [])]
    ast = extract(code, cache_root=root, root=root) if code else dict(EMPTY)
    write_json(out / ".graphify_ast.json", ast)
    semantic = [str(Path(p).resolve()) for kind in ("document", "paper", "image") for p in detected.get("files", {}).get(kind, [])]
    cached_n, cached_e, cached_h, uncached = check_semantic_cache(semantic, root=root, prompt_file=spec)
    cached_e, cached_h, pruned_edges, pruned_hyperedges = prune_dangling_cached(
        ast, cached_n, cached_e, cached_h
    )
    write_json(out / ".graphify_cached.json", {"nodes": cached_n, "edges": cached_e, "hyperedges": cached_h})
    images = {str(Path(p).resolve()) for p in detected.get("files", {}).get("image", [])}
    normal = sorted((p for p in uncached if p not in images), key=lambda p: (str(Path(p).parent), p))
    groups = chunk_sources(normal, args.chunk_size, args.chunk_bytes)
    groups.extend([[source_record(p)] for p in sorted(images.intersection(uncached))])
    chunks = []
    for i, sources in enumerate(groups, 1):
        filename = f".graphify_chunk_{i:02d}.json"
        output = out / filename
        output.unlink(missing_ok=True)
        chunks.append({
            "number": i,
            "total": len(groups),
            "files": [source["source_file"] for source in sources],
            "sources": sources,
            "size_bytes": sum(source["size_bytes"] for source in sources),
            "output": str(Path(args.out) / filename),
            "deep": args.deep,
        })
    manifest = {
        "graphify_version": version,
        "project_root": str(root),
        "spec": str(spec),
        "contract": contract,
        "chunks": chunks,
    }
    write_json(out / ".graphify_chunks.json", manifest)
    if not chunks:
        write_json(out / ".graphify_semantic_new.json", EMPTY)
    print(json.dumps({"graphify": version, "code_files": len(code), "semantic_files": len(semantic), "cached_files": len(semantic) - len(uncached), "chunks": len(chunks), "pruned_cached_edges": pruned_edges, "pruned_cached_hyperedges": pruned_hyperedges}))


if __name__ == "__main__":
    main()
