#!/usr/bin/env python3
"""Best-effort code refresh and semantic-refresh signal after a Git commit."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone


SEMANTIC_EXTENSIONS = {
    ".md", ".mdx", ".qmd", ".skill", ".txt", ".rst", ".html", ".yaml", ".yml",
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".docx", ".xlsx",
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".mp3", ".wav", ".m4a", ".ogg",
}


def emit(status, **details):
    print(json.dumps({"graphify_post_commit": status, **details}, ensure_ascii=False))


def current_head(root):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def record_result(path, commit, status, attempts=1, **details):
    path.write_text(json.dumps({"commit": commit, "status": status, "attempts": attempts,
                                **details}, indent=2), encoding="utf-8")
    emit(status, commit=commit, attempts=attempts, **details)


def committed_semantic_files(root):
    result = subprocess.run(
        ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return [], "git_diff_failed"
    files = [name for name in result.stdout.split("\0") if name]
    return sorted(name for name in files if Path(name).suffix.lower() in SEMANTIC_EXTENSIONS), None


def graph_counts(path):
    """Return portable graph totals, or None when no readable graph exists."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
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
    if before is None or after is None:
        return None
    return {
        "before": before,
        "after": after,
        "delta": {key: after[key] - before.get(key, 0) for key in after},
    }


def record_code_refresh(root):
    """Advance the code head without hiding un-ingested semantic changes.

    semantic_head is the last commit whose documents were semantically ingested.
    Pin it to the previous head before advancing head, so a later code-only
    commit cannot make a graph with pending semantic changes look current.
    """
    head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False)
    state_path = root / "graphify-out" / ".claude_graph_state.json"
    state = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
    if state.get("head") and not state.get("semantic_head"):
        state["semantic_head"] = state["head"]
    state.update({"head": head_result.stdout.strip() if head_result.returncode == 0 else None,
                  "generated_at": datetime.now(timezone.utc).isoformat()})
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", nargs="?", default=".", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    root = args.project_root.resolve()
    graph = root / "graphify-out" / "graph.json"
    marker = root / "graphify-out" / ".claude_post_commit.json"
    commit = current_head(root)
    semantic_files, detection_error = committed_semantic_files(root)

    if not graph.is_file():
        emit("skipped", reason="graph_missing", semantic_files=semantic_files)
        return 0
    before_counts = graph_counts(graph)

    previous, attempts = {}, 1
    if marker.is_file():
        try:
            previous = json.loads(marker.read_text(encoding="utf-8"))
            if commit and previous.get("commit") == commit:
                previous_status = previous.get("status")
                if previous_status in {"updated", "semantic_refresh_required", "skipped"}:
                    emit("already_processed", commit=commit, previous_status=previous_status,
                         semantic_files=previous.get("semantic_files", []))
                    return 0
                attempts = int(previous.get("attempts", 1)) + 1
                if previous_status == "failed" and attempts > 2:
                    emit("retry_exhausted", commit=commit, previous_status=previous_status,
                         attempts=attempts - 1, semantic_files=previous.get("semantic_files", []))
                    return 0
        except (OSError, ValueError):
            previous, attempts = {}, 1

    executable = shutil.which("graphify")
    if not executable:
        record_result(marker, commit, "failed", attempts=attempts, reason="graphify_not_on_path",
                      semantic_files=semantic_files)
        return 0

    try:
        result = subprocess.run(
            [executable, "update", "."],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        record_result(marker, commit, "failed", attempts=attempts, reason="timeout", timeout_seconds=args.timeout,
                      semantic_files=semantic_files)
        return 0
    except OSError as exc:
        record_result(marker, commit, "failed", attempts=attempts, reason="execution_error", detail=str(exc),
                      semantic_files=semantic_files)
        return 0

    if result.returncode == 0:
        delta = graph_delta(before_counts, graph_counts(graph))
        record_code_refresh(root)
        if semantic_files:
            record_result(marker, commit, "semantic_refresh_required", attempts=attempts, code_refresh="updated",
                          semantic_files=semantic_files, graph_delta=delta,
                          detection_warning=detection_error)
        else:
            record_result(marker, commit, "updated", attempts=attempts, graph_delta=delta,
                          detection_warning=detection_error)
    else:
        detail = (result.stderr or result.stdout or "unknown error").strip()[-500:]
        record_result(marker, commit, "failed", attempts=attempts, reason="update_failed", returncode=result.returncode,
                      detail=detail, semantic_files=semantic_files)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
