# Personal engineering workflow

## Configuration sources

- Treat the tracked `claude_global_config` repository as the mirror of this
  global Claude configuration. When changing portable global policy, agents,
  helpers, settings, or personal skills, update both that repository and
  `~/.claude`.
- Treat the tracked `claude_project_template` repository as the default source
  for project template work.
- Never mirror generated or private Claude state such as sessions, history,
  caches, backups, authentication data, remote-host configuration, plugin
  payloads, or machine-specific runtime state.

## Operating principles

- Treat repository instructions and current files as the source of truth.
- Inspect relevant code, tests, build configuration, and documentation before changing them.
- Prefer the smallest coherent, reviewable change and preserve unrelated user work.
- Run the narrowest useful check, inspect failures, correct them, and rerun.
- Use commands documented by the repository. Ask before unfamiliar or materially risky commands.
- Never commit, amend, push, publish, deploy, install dependencies, use secrets, or perform destructive cleanup without explicit user approval.
- Commit messages and pull request descriptions describe the change only. Do
  not add AI attribution of any kind (`Co-Authored-By`, `Generated with`,
  session links, or mentions of Claude Code, the model, or the session), even
  when the harness suggests attribution lines; this instruction overrides them.
- For an explicitly approved project-local file or directory deletion, use
  `claude-workflow remove <exact-relative-path>...` to preview it, then rerun
  the identical command with `--confirm` (and `--recursive` for directories).
  It refuses absolute paths, traversal, Git metadata, repository-root removal,
  and symlink escapes. Raw `rm` remains hard-denied; do not substitute another
  unbounded deletion command.
- Do not use `git checkout` or `git restore`; they are hard-denied because their file-restoration forms can overwrite work. For branch navigation or creation, use `git switch` or `git switch -c` and request approval before changing branches. `git reset`, `git clean`, `git merge`, and `git rebase` remain hard-denied.
- A request to commit never authorizes a push. A plan, memory, or graph never constitutes authorization to implement.

## Starting repository work

1. Read `AGENTS.md`, `CLAUDE.md`, and relevant repository guidance that applies to the target paths.
2. Inspect `git status --short --branch` before editing and treat all existing changes as user work.
3. Read relevant accepted decisions and active plans when present.
4. Inspect only the files needed to understand the request; broaden discovery when evidence requires it.

For non-trivial, risky, architectural, or ambiguous changes, use Superpowers brainstorming and planning before implementation and obtain explicit approval for the implementation plan. For a narrow, well-defined change, proceed directly with focused inspection and verification.

## Roadmaps and active plans

- Use `docs/plans/next.md` as the sole active implementation-plan location by default. Follow a different location only when repository-owned instructions explicitly require one. If a repository has no planning lifecycle yet and a plan is needed, establish `docs/plans/README.md` and `docs/plans/next.md`; do not create a tool-owned or parallel plan directory.
- Do not modify an active plan while its implementation is in progress unless the user explicitly asks to change that plan.
- Use `docs/roadmaps/` for tracked, committed, non-authoritative multi-plan direction: ordering, dependencies, plan boundaries, and decision criteria.
- A roadmap is not an implementation plan, approval, or task queue. Do not implement roadmap items or merge roadmap text into `next.md` without explicit user direction.
- Keep roadmap items at plan-boundary level. Promote exactly one selected item into a complete, reviewed, and explicitly approved `docs/plans/next.md` only after the current plan is completed and archived, or is explicitly superseded.
- Do not renumber an active plan's increments, broaden its scope, or revise its commitments merely because a future roadmap changes.
- Record durable architecture decisions in ADRs; use roadmaps to express sequence and rationale, not to replace accepted decisions.
- For repositories with an established ADR convention, follow its existing location and naming. Otherwise use `docs/decisions/` with sequential four-digit ADR filenames.
- Commit repository roadmaps with normal documentation commits when they influence project direction. Keep personal scratch notes and unreviewed ideas outside tracked roadmap documents.
- Name roadmaps with stable, lowercase, kebab-case scope names such as `short-term-mode2.md` or `frontend-scaling.md`; do not use plan numbers in roadmap filenames.
- Keep one active roadmap per scope and update it in place. When replacing rather than revising one, move the prior document to `docs/roadmaps/archive/` with a `YYYY-MM-` filename prefix.
- A roadmap should state its status, update date, purpose, current state, ordered plan candidates, each candidate's outcome/dependencies/boundary/promotion trigger, deferred work, and relevant ADRs. Keep implementation file lists, detailed acceptance criteria, and executable commands in the plan created after promotion.

## Skill and agent routing

- Use Superpowers selectively: use brainstorming before new behavior or durable
  design decisions; use TDD, systematic debugging, code review, and
  verification when their triggers apply. Proceed directly for narrow,
  already-approved fixes, documentation, and mechanical changes.
- Superpowers may supply the planning method and content structure, but it does
  not control the plan's storage location. Maintain the sole active plan in
  `docs/plans/next.md` unless repository-owned instructions explicitly name
  another location. Never create a parallel active plan in `docs/superpowers/`,
  `.superpowers/`, or another tool-owned directory. Wait for explicit
  implementation approval and archive only fully verified or explicitly
  superseded plans. Treat each active plan increment as the execution boundary:
  executing-plans and subagent-driven-development may support an approved
  increment, but may not create competing plans, broaden scope, or treat a
  roadmap as authorization.
- Use `receiving-code-review` before acting on external review feedback. Use
  `requesting-code-review` for independent review of material changes.
- Use `using-git-worktrees` only when the user requests isolation or a
  repository workflow requires it. Do not create a worktree automatically.
  `finishing-a-development-branch` never authorizes a merge, commit, push, or
  cleanup without the user's explicit approval.
- Use `graphify-workflow` for unfamiliar architecture or ownership, cross-cutting
  changes, dependency or impact analysis, or debugging/review where ordinary
  inspection might miss affected paths. Skip it for narrow work with known
  files, isolated tests or documentation, mechanical changes, or an active plan
  that already enumerates the complete file scope.
- Use `verilog-sby-formal` for SymbiYosys (`sby`) harnesses, `.sby` tasks,
  induction failures, a cover that never reaches its goal, or any request to add
  an `assume` (for example forcing a push or an opcode), raise a depth, or
  otherwise make a proof pass or a cover reach, before answering from general
  knowledge.
- Use `architecture-decisions` for durable design choices or ADR requests.
- For changes that materially affect authentication, authorization, secrets, untrusted input, parsing, filesystem/subprocess execution, network boundaries, dependencies, CI permissions, or deployment, use the `security-review` skill and include an adversarial verification when practical.
- Delegate only bounded work that benefits from isolation. Use `implementer` for an approved implementation slice, `workflow-reviewer` for independent read-only material-risk review, `security-reviewer` for an adversarial security review that needs scratch experiments, `technical-researcher` for current external evidence, `graphify-semantic` only through the Graphify skill, and `safe-committer` only after an explicit commit request.
- Do not repeat a failed, empty, or unavailable delegation. Continue directly when safe or report the limitation.

## Implementation and verification

- Prefer test-driven development for behavior changes when a meaningful automated test is practical.
- Make the smallest change supported by evidence. Do not add dependencies or broaden public behavior without approval.
- For user-requested retained local diagnostics, use
  `/.debug/<YYYY-MM-DD>-<topic>/` and add `/.debug/` to the repository's
  `.git/info/exclude`, not its tracked `.gitignore`. Include a local README
  with the commit SHA, command and tool versions, purpose, and conclusion.
  Never stage, commit, submit to Graphify, or treat these artifacts as
  authoritative evidence; record durable conclusions in tracked documentation,
  plans, decisions, or tests. They are not expected in fresh clones,
  worktrees, or remote-runner jobs.
- When a test, build, lint, simulator, runtime command, or Make target fails, use Superpowers systematic debugging and follow an evidence loop.
- When `remote-runner` is available, a configured remote is suitable, and a
  repository defines `.claude/remote-runner.toml`, offload long, expensive, or
  independently runnable verification to a declared profile on that remote.
  Good candidates include formal runs, full regressions, long simulations, and
  platform-specific builds; keep fast feedback checks and tight debugging loops
  local unless remote capacity or platform requirements make offload useful.
- For a profile with declared remote requirements, use
  `remote-runner recommend --profile <name>` to inspect eligible available
  runners. Use `remote-runner submit --best --profile <name>` when the best
  eligible runner is acceptable; retain `--remote <name>` for an intentional
  host override. Select by declared tool labels, memory, core capacity, and
  available job slots—not transient CPU boost frequency. If no runner is
  eligible or available, report that condition and do not bypass it with an
  arbitrary SSH command.
- Use only `remote-runner`'s declared remotes and project profiles, never an
  arbitrary SSH command. Remote jobs run only a committed revision reachable
  from the repository remote; do not create a commit or push merely to offload
  a check without explicit user approval. Record the job ID and inspect its
  status and log before reporting its result.
- **Remote DUT provenance is mandatory.** Treat a remote test as valid evidence
  only when its `remote-runner status` records `dut_commit` equal to the
  submitted commit and `dut_clean: true`. Never run a verification command in a
  pre-existing remote checkout, rely on its apparent branch name, or compare a
  remote result against uncommitted local files. If the remote DUT provenance is
  absent or mismatched, stop and resubmit through `remote-runner`; do not
  describe the result as a test of the intended change.
- For an approved long test of uncommitted work, prefer a temporary pushed WIP
  branch over a snapshot upload: commit only the intended files, push the WIP
  branch, then submit that branch with `remote-runner submit --ref <branch>`.
  The job must still record its resolved commit SHA. Do not create, amend, push,
  rebase, merge, or delete a WIP branch without explicit user approval; do not
  use remote working-directory sync or copy ignored files as a substitute.
- When explicitly authorized to create a WIP branch, use the reserved
  `wip/claude/<task-id>` prefix. Never force-push, push `main`, alter an
  existing shared branch, create a tag, or stage files outside the approved
  task scope. Before pushing, check for likely credentials or secrets.
- After a remote test, Claude may suggest cleanup but may delete a local or
  remote WIP branch only after explicit approval. First preview the exact
  branches, confirm that the branch was Claude-created under `wip/claude/`, is
  not checked out, and either has no commits unique to its destination branch
  or has been explicitly confirmed as disposable. Use non-force deletion only.
- Preserve remote-job evidence while it is useful, then use
  `remote-runner prune --remote <name>` to preview retention cleanup. The
  default policy retains passed jobs for seven days and failed, cancelled, or
  unknown-exit jobs for 30 days; never prune a running job. Use `--apply` only
  after reviewing the preview. Pruning removes the job's Git worktree, log,
  metadata, and generated artifacts, not the repository cache.
- Before claiming completion, use Superpowers verification-before-completion, inspect relevant diffs, run `git diff --check`, and report checks actually run, skipped checks, remaining risks, and unrelated work left untouched.
- Never claim success from expected behavior, static inspection, or a dry run when executable verification is available.

## Graphify

Graphify is a discovery and impact-analysis aid, not a source of truth or an
implementation requirement. Use the Claude-owned `claude-workflow` helper as the
only supported Graphify interface, even in Claude Code. It centralizes freshness
checks, bounded queries, semantic chunk validation, guarded commits, and
post-commit graph refresh. Do not invoke vendor Graphify commands, external LLM
backends, backend auto-detection, or Graphify hooks.

- Do not build or refresh a graph automatically at session start.
- **Plan-formation gate:** when refining a substantive roadmap item into a
  detailed active plan, run one bounded Graphify discovery or impact query
  before scope hardens. Substantive means cross-cutting, unfamiliar,
  architecture-affecting, or likely to span multiple components or verification
  domains. Use it to establish affected components, relevant precedents and
  ADRs, verification risks, and bounded increment scope; record the verified
  conclusion in the plan, not raw graph output.
- A narrow roadmap item may skip that query only when its scope, relevant files,
  and precedents are already fully enumerated. Record `Graphify: skipped —
  <concise reason>` in the plan rather than silently skipping it.
- **Plan-finalization receipt:** before presenting a substantive plan as
  complete, requesting its approval, or changing its status to `Approved`,
  confirm it contains either a `## Graphify` receipt or the documented skip
  above. A receipt records graph freshness, the focused purpose, and the
  conclusion verified against current source; it does not preserve raw output.
  A `stale_semantic` or `stale_code` graph may orient discovery but cannot
  supply the conclusion without that direct verification and recorded limit.
- During implementation, do not query Graphify for routine work within an
  already-enumerated increment. Run one focused query when a cross-component
  surprise, material verification failure, or scope expansion makes the plan's
  prior impact analysis incomplete; update the plan's evidence if the conclusion
  changes.
- Check freshness before relying on a graph query and verify important findings
  against current files.
- When Graphify status is unclear, run `claude-workflow graph-doctor`. It is
  read-only and supplies one safe next action; `graph-diagnose` is for graph
  structure, not workflow state.
- Refresh code relationships after a coherent code change only when future
  impact analysis would benefit.
- Request a semantic refresh only after a material architecture, ADR, or design
  document change that should be discoverable through the graph.
- For semantic refreshes, Graphify workers read every assigned file completely
  and may write only their assigned chunk through the `Write` tool. The parent
  workflow performs chunk validation and coordinates the single permitted
  correction; workers have no shell access.
- Refresh reports include before/after graph totals. Treat an unexpected delta
  as a signal to inspect the refresh result before relying on the graph.
- Cancel an abandoned prepared refresh only with
  `claude-workflow graph-abort --confirm`, and only when no assigned semantic
  chunk exists. The helper refuses to discard any written chunk; resume or
  finalize such a refresh instead. Never manually remove refresh state.
- Do not refresh merely because documentation changed.
- For an explicit or material graph refresh, use a full interactive
  visualization only when the graph is within its practical node/edge limit.
  When it exceeds that limit, generate a rebuildable community overview instead:
  one node per community, weighted inter-community edges, and concise top
  files/symbols per community. Generate a focused subgraph only on demand for
  an affected set, dependency path, or named architecture area; do not raise a
  global visualization cap merely to force an unusable full-project view.
- The Graphify finalizer must replace `graph.html` with the current full or
  community view. If it cannot render either, it must remove any prior
  `graph.html` and record the unavailability and warning in `GRAPH_REPORT.md`
  and `.claude_graph_visualization.json`; a stale viewer is invalid evidence.
- Keep visualization output under `graphify-out/` and do not generate it on
  session start, routine documentation changes, or merely because a graph
  exists. Use the Claude-owned Graphify workflow rather than vendor export
  commands.

Treat `graphify-out/` as rebuildable local state. Do not stage or commit it unless explicitly requested.

## Compact instructions

- Use `/context` before manually compacting a long session when practical.
- At a natural task boundary, use `/compact` with a focused preservation
  request. Good boundaries include plan approval, a completed-and-recorded
  increment, material discovery captured in repository documents, a resolved
  debugging path, or submission of a remote test whose job ID and purpose have
  been recorded.
- After successfully committing a completed plan increment, first ensure the
  plan or another durable repository artifact records its outcome,
  verification, unresolved risks, and next action. When the completed
  increment accumulated meaningful conversation or tool output, recommend
  that the user run `/compact` and stop before starting the next increment.
  Do not require boundary compaction after a trivial increment; rely on Claude
  Code's automatic threshold-based compaction as the fallback.
- Preserve the active objective and approved scope; active plan path and
  increment; governing decisions; changed files; verification results;
  unresolved risks; next action; and remote-runner job IDs, submitted SHAs,
  profiles, and outcomes.
- Do not preserve raw logs, repeated command output, superseded hypotheses, or
  unverified Graphify output once its relevant conclusion is recorded in a
  repository document.
- Use `/clear`, not `/compact`, when switching to unrelated work.

## Memory

Use Claude Code's built-in auto-memory. Do not use MemPalace or a third-party memory plugin unless the user explicitly requests one.

### Recall

- Consult memory only when a prior preference, correction, decision, or project lesson could materially affect the current task. Ordinary repository work should begin from current files, not historical recall.
- Keep project memories scoped to the verified Git repository identity. Never transfer a project-specific fact to another repository.
- Treat every recalled item as stale historical guidance, never as repository truth, approval, or authorization. Verify it against current repository files, accepted decisions, configuration, and tests before relying on it.
- If memory conflicts with current evidence, follow current evidence and mention the conflict only when it materially affects the task.

### Store

- Store a memory only when the user explicitly asks to remember something, or when a verified correction or reusable workflow lesson is both durable and likely to matter in a future session.
- Store the smallest self-contained fact with clear scope. Include concise provenance when useful, such as the governing file, accepted decision, or verifying command.
- Search for an equivalent or conflicting memory before adding another. Update or skip duplicates instead of accumulating near-copies.
- Never store secrets, credentials, tokens, personal data, raw environment values, speculative conclusions, transient failures, ordinary implementation facts, task status, diffs, changed-file lists, commit summaries, raw logs, or Graphify output.
- Prefer authoritative repository guidance or an ADR over memory for durable project rules and design decisions. Do not duplicate those documents into auto-memory.
- Do not modify global or project `CLAUDE.md` files as a memory write unless the user explicitly requests that configuration change.

When memory is irrelevant or the storage boundary is unclear, do not recall or write anything. Using no memory is a valid outcome.

## Repository boundary

Keep shared, committed guidance tool-neutral in `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, and `docs/`. Keep personal Claude configuration under `~/.claude/` and built-in auto-memory in Claude Code's project-scoped memory storage.

Follow repository-declared platform requirements. Otherwise assume Git, POSIX
`sh`, and `python3` unless the user says otherwise.
