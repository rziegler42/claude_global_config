---
name: graphify-workflow
description: Query, build, refresh, or diagnose Graphify project graphs for
  unfamiliar architecture, cross-cutting impact, or dependency analysis. Run
  one bounded query when forming a substantive plan; skip narrow work with
  documented rationale and routine work within an enumerated increment.
---

# Graphify workflow

Use the Claude-owned `claude-workflow` helper as the only supported Graphify
interface.

Graphify is a discovery and impact-analysis aid, not a source of truth or an
implementation requirement. Do not use it automatically at session start.

## When to use it

**Plan formation:** Before writing a detailed plan for substantive roadmap
work, run exactly one focused discovery or impact query. Substantive work is
cross-cutting, unfamiliar, architecture-affecting, or likely to span multiple
components or verification domains. Use the result to bound increments and
identify affected components, relevant precedents/ADRs, and verification risk.
Record the verified conclusion in the plan, not raw graph output.

For a narrow item whose scope, files, and precedents are already fully
enumerated, skip the query and record `Graphify: skipped — <concise reason>` in
the plan.

**Implementation:** Do not query Graphify for routine work inside an
already-enumerated increment. Run one focused query if a cross-component
surprise, material verification failure, or scope expansion invalidates the
plan's prior impact analysis; update the plan evidence only if its conclusion
changes.

**Other discovery:** Use Graphify when architecture or ownership is unfamiliar;
a change, refactor, ADR, or review spans components; dependency or impact
analysis is needed; or ordinary inspection might miss relevant paths during
debugging or review. Skip it for isolated tests or documentation and mechanical
changes with known file scope.

## Query

From the repository root, run `claude-workflow graph-status`. Treat anything
except `current` as potentially stale. Ask about one relationship anchored on
one component, symbol, document, or decision at a time. Do not combine
ownership, dependencies, implementation files, tests, plans, and ADRs into one
compound question. Start with exactly one focused operation:

- impact: `claude-workflow graph-affected "<node>"`
- component: `claude-workflow graph-explain "<node>"`
- dependency flow: `claude-workflow graph-path "<source>" "<target>"`
- broad orientation: `claude-workflow graph-query "<question>"`
- diagnostics: `claude-workflow graph-diagnose`

Prefer `graph-explain` for ownership or component context, `graph-affected` for
dependents or impact, and `graph-path` for a relationship between two known
nodes. Use `graph-query` only for broad orientation when the correct anchor is
not yet known.

Use a second graph call only when the first exposes a material unresolved
relationship. The normal one-query limit permits one automatic narrowing
follow-up after a truncated result. Treat `[!] TRUNCATED` as incomplete output,
not an error and not sufficient evidence for a conclusion:

1. Do not answer from the partial traversal alone.
2. Select one specific returned node as the next anchor.
3. Narrow with `graph-explain`, `graph-affected`, or `graph-path`.
4. Increase `graph-query --budget` only if that narrowed query still truncates.

Keep the default 2,000-token budget; do not compensate for a compound query by
raising it first. Never pipe Graphify output through `head`, `tail`, `cut`, or
another output-clipping command because that can silently hide relationships or
the truncation warning. If the narrowed follow-up remains truncated, state that
limitation and independently verify every reported conclusion against current
repository files.

A stale graph is discovery evidence, not current truth; refresh first only when
current relationships materially affect the answer.

Never invoke vendor Graphify commands directly, inspect their help, select an
external LLM backend, use backend auto-detection, or install hooks.

## Build or refresh

Build or refresh only when current code relationships will provide future
impact-analysis value. After material architecture, ADR, or design-document
changes, request a semantic refresh only if that change should be discoverable
through the graph. Do not refresh merely because documentation changed.

1. Run `claude-workflow graph-prepare` (`--deep` only when requested).
2. Read `graphify-out/.graphify_chunks.json` once. It contains the complete
   contract.
3. If there are chunks, dispatch every chunk to the `graphify-semantic` agent,
   preferably in parallel. Pass only its file list, exact output path, deep
   flag, per-file size and SHA-256 records, and manifest contract. The worker
   must read every assigned file in full, using paged reads through EOF when
   necessary, and must not write a provisional chunk.
4. Accept a worker handoff only when it returns exactly `COMPLETE <assigned-path>
   coverage <N>/<N>` with the expected path and assigned-file count. An output
   file without that completion report remains incomplete and must not be
   validated or finalized. If a worker stops at its turn limit or returns
   `INCOMPLETE`, resume that same worker with: `Continue the existing chunk
   assignment. Determine which assigned files have not reached EOF, read all
   remaining content using paged reads, and do not write or revise the chunk
   until every assigned file is complete. Then write the assigned output and
   return the required COMPLETE report.` Never instruct a worker to skip,
   abbreviate, assume, or avoid re-reading source content.
5. The parent validates each completed path with exactly
   `claude-workflow graph-validate-chunk <assigned-path>`. If it fails, send the
   exact failure to the original worker for one focused `Edit` of that same
   path, then validate once more. A denied write, missing output, or second
   validation failure stops the refresh without finalizing. Workers have no
   shell access and may never use a script or Bash command to write a chunk.
   Treat validator-reported counts as authoritative; ignore worker hand tallies.
   Coverage validation proves exact prepared sources were acknowledged at their
   prepared hashes, not that the semantic interpretation is complete.
6. After every worker has returned a completion report and every chunk has
   validated, run `claude-workflow graph-finalize` directly. Finalization must
   refuse any missing, stale, structurally invalid, or coverage-incomplete
   chunk.
7. Report graph size, failed chunks, visualization mode, and commands actually
   run. `graph.html` is current only when the finalizer reports a generated
   visualization; otherwise consult `GRAPH_REPORT.md` and
   `.claude_graph_visualization.json`, never a prior viewer.

Do not independently rewrite worker output, reuse a failed old chunk, or ask
for chunk JSON in chat. Parent-side validation is required; it is not an
independent semantic rewrite.

## After a commit

The guarded commit helper performs a best-effort local graph refresh and
returns a structured Graphify result. Do not make a second post-commit call
when that object exists. If a successful content-commit report lacks it, run
`claude-workflow graph-post-commit` at most once. Deferred semantic refresh
does not invalidate a successful commit.

Treat `graphify-out/` as rebuildable local state; never stage or commit it automatically.
