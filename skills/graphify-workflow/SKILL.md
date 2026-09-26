---
name: graphify-workflow
description: Use when forming a substantive plan, investigating unfamiliar
  architecture or ownership, tracing cross-component impact or dependencies,
  or when asked to query, build, refresh, or diagnose the Graphify project
  graph (`graphify-out/`, `claude-workflow graph-*`).
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

**Plan finalization:** Before presenting a substantive plan as complete,
requesting approval, or changing its status to `Approved`, confirm it contains
either a `## Graphify` receipt or the documented skip above. A receipt records
graph freshness, the focused purpose, and the conclusion verified against
current source; do not preserve raw output. A graph with any status other than
`current` (`stale_semantic`, `stale_code`, `present`, `refresh_in_progress`) may
orient discovery but cannot supply that conclusion without direct verification
and a recorded limitation.

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
except `current` as potentially stale:

| Status | Meaning and action |
|---|---|
| `current` | Graph matches the last refresh. |
| `stale_code` | Code changed since the last refresh; orient with it, verify against source. |
| `stale_semantic` | Documents changed and are not yet ingested; same as above. It persists across later code-only commits until a semantic refresh runs. |
| `present` | Freshness metadata is missing or invalid, or its baseline commit no longer resolves (the warning says which); treat as stale. |
| `refresh_in_progress` | A prepared refresh exists; run `graph-doctor` for the next action. |
| `missing` | No graph. Queries fail. Do not build one automatically; rely on source inspection unless a build has value (see Build or refresh). |

Ask about one relationship anchored on one component, symbol, document, or
decision at a time. Do not combine ownership, dependencies, implementation
files, tests, plans, and ADRs into one compound question. Start with exactly
one focused operation:

- impact: `claude-workflow graph-affected "<node>"`
- component: `claude-workflow graph-explain "<node>"`
- dependency flow: `claude-workflow graph-path "<source>" "<target>"`
- broad orientation: `claude-workflow graph-query "<question>"`
- diagnostics: `claude-workflow graph-diagnose`

Prefer `graph-explain` for ownership or component context, `graph-affected` for
dependents or impact, and `graph-path` for a relationship between two known
nodes. Use `graph-query` only for broad orientation when the correct anchor is
not yet known.

`graph-explain`, `graph-path`, and `graph-affected` have no token budget, and
output must not be clipped. Bound them with their own options instead:
`graph-affected --depth 1` and repeated `--relation <name>` (for example
`calls`, `references`, `imports`, `uses`, `requires`) for a hub node, and
`graph-query --context <filter>` (repeatable) or `--dfs` to steer a query.
`graph-god-nodes` and `graph-benchmark` also exist but are not part of routine
work; use them only when asked.

No helper command produces a focused subgraph or community overview on demand;
the finalizer writes only the refresh-time `graph.html`. If one is requested,
report that it is unavailable instead of using vendor export commands.

Use a second graph call only when the first exposes a material unresolved
relationship. The normal one-query limit permits one automatic narrowing
follow-up after a truncated result. Treat the leading `[!] TRUNCATED: showing X
of Y nodes` line (also echoed as a trailing `... (truncated — N more nodes cut
...)` line) as incomplete output, not an error and not sufficient evidence for
a conclusion. Its `context_filter` hint is the helper's `--context` option; its
`get_node` hint is not exposed, so use `graph-explain` instead:

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

If a query returns no usable matching node or relationship, do not treat that
as evidence of absence and do not retry with guessed synonyms. Select one exact
component, symbol, filename, or decision title from current repository files,
then use one narrowed `graph-explain`, `graph-affected`, or `graph-path` call.
If no exact anchor exists, report that the graph supplied no evidence and rely
on current source inspection instead.

A stale graph is discovery evidence, not current truth; refresh first only when
current relationships materially affect the answer.

Never invoke vendor Graphify commands directly, inspect their help, select an
external LLM backend, use backend auto-detection, or install hooks.

Use `claude-workflow graph-doctor` when Graphify status is unclear. It is
read-only and reports the workflow state plus one safe next action; it never
refreshes, finalizes, deletes, or rebuilds. Use `graph-diagnose` only for
structural graph analysis, not refresh-state diagnosis.

## Build or refresh

Build or refresh only when current code relationships will provide future
impact-analysis value. After material architecture, ADR, or design-document
changes, request a semantic refresh only if that change should be discoverable
through the graph. Do not refresh merely because documentation changed.

Before running `graph-prepare`, read `references/refresh.md` and follow it
exactly: prepare, dispatch every chunk to the `graphify-semantic` agent,
validate each chunk, then finalize. Never remove refresh state or manifests
manually; use `claude-workflow graph-doctor` for the next safe action.

## After a commit

The guarded commit helper performs a best-effort local graph refresh and
returns a structured Graphify result. Do not make a second post-commit call
when that object exists. If a successful content-commit report lacks it, run
`claude-workflow graph-post-commit` at most once. Deferred semantic refresh
does not invalidate a successful commit. A `semantic_refresh_required` result
keeps the graph `stale_semantic`, even after later code-only commits, until a
semantic refresh finalizes.

Paths the graph never ingests (`.graphifyignore`, `.gitignore`, skip files) do not
affect freshness or the semantic-refresh signal. Keep working files that change while
the graph is queried, such as `docs/plans/next.md`, in `.graphifyignore`. Adding a
rule does not remove nodes already in the graph; they disappear at the next semantic
refresh. If the ignore helper cannot run, nothing is filtered and the graph reads as stale.

Treat `graphify-out/` as rebuildable local state; never stage or commit it automatically.
