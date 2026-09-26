#!/usr/bin/env python3
"""Print which repository-relative paths (JSON list on stdin) Graphify's ignore rules exclude.

Uses Graphify's own predicate, so .graphifyignore, .gitignore, skip files, and noise
directories are judged exactly as `detect()` judges them. Exits non-zero when the
Graphify runtime is unavailable; callers then filter nothing.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys


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
    raise SystemExit("Graphify runtime not found")


ensure_graphify_runtime()

from graphify.detect import ignored_predicate


def main():
    root = Path(sys.argv[1]).resolve()
    paths = json.load(sys.stdin)
    ignored = ignored_predicate(root)
    print(json.dumps(sorted(path for path in paths if ignored(root / path))))


if __name__ == "__main__":
    main()
