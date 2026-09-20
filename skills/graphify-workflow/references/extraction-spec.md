# Semantic extraction contract

Read every assigned file completely. For a long file, use paged reads until EOF;
reading only changed hunks, an opening section, or an index tail is insufficient.
Write only the exact assigned chunk path as JSON, with no prose or Markdown.

Schema:

`{"coverage":[],"nodes":[],"edges":[],"hyperedges":[],"input_tokens":0,"output_tokens":0}`

`coverage` must contain exactly one entry for every assigned file and no other
file: `{"source_file":"<exact assigned absolute path>","sha256":"<exact
manifest digest>","status":"read_complete"}`. Add an entry only after reading
that source through EOF. Never write a partial chunk to preserve progress; if
any source is incomplete, report the incomplete paths without writing output.

Each node requires `id`, `label`, `file_type`, and `source_file`. `file_type` is one of `code`, `document`, `paper`, `image`, `rationale`, or `concept`. IDs are lowercase `[a-z0-9_]`, derived deterministically from the full repository-relative source path plus entity name; never add chunk or sequence suffixes.

Each edge requires `source`, `target`, `relation`, `confidence`, `confidence_score`, and `source_file`. Confidence is `EXTRACTED`, `INFERRED`, or `AMBIGUOUS`. EXTRACTED scores 1.0; INFERRED uses 0.95, 0.85, 0.75, 0.65, or 0.55; AMBIGUOUS uses 0.1 through 0.3. Calls point caller to callee and never cross programming languages.

Each hyperedge requires `id`, `label`, at least three `nodes`, `relation`, `confidence`, `confidence_score`, and `source_file`; use at most three per chunk.

Every `source_file` must exactly equal one of the absolute assigned paths. Extract named entities, concepts, rationale, citations, and useful non-obvious semantic relationships. Do not duplicate code imports or other relationships already available from syntax analysis. In deep mode, include more indirect relationships but mark uncertainty honestly.
