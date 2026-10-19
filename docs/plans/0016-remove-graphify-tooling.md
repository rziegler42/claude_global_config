# 0016: Remove the Graphify tooling from the global configuration

Status: Completed
Created: 2026-10-19
Completed: 2026-10-19

## Goal

Remove the Graphify tooling from the global configuration now that the template's
`graphify` module ships it (template roadmap candidate 5, commit `4348bc8` there). After
the plan, `claude-workflow` keeps `commit`, `amend-message`, `remove`, `context` and
`project-id`, and no helper, skill, agent, permission rule or policy here depends on Graphify.
The only Graphify words that remain are the intentional ones listed under Completion criteria.

## Scope

- `bin/claude-workflow`: remove every `graph-*` command (`graph-status`, `graph-doctor`,
  `graph-prepare`, `graph-abort`, `graph-finalize`, `graph-post-commit`, `graph-query`,
  `graph-path`, `graph-explain`, `graph-affected`, `graph-god-nodes`, `graph-diagnose`,
  `graph-benchmark`, `graph-validate-chunk`) and their helpers (`graph_script`,
  `graph_ignored_paths`, `graph_status_details`, `require_graph_output`, the chunk
  validation code). In `commit`, drop the post-commit Graphify step and the `graphify` key of
  its result. In `context`, drop the `graphify` key. `dirty_paths` stops special-casing
  `graphify-out/`.
- Delete `skills/graphify-workflow/` (SKILL.md, references, scripts, and its tests) and
  `agents/graphify-semantic.md`, with their lines in `config-manifest.txt`.
- `settings.json`: remove the eleven `Bash(claude-workflow graph-…:*)` allow rules.
- `hooks/codex_approver.py`: drop `graph-doctor graph-diagnose graph-abort` from the
  `claude-workflow` subcommand set.
- `agents/safe-committer.md`: drop the two sentences about the structured Graphify result.
- `skills/architecture-decisions/SKILL.md`: reword the two Graphify mentions (discovery aid;
  the semantic-refresh recommendation in step 8).
- `CLAUDE.md` (and `~/.claude/CLAUDE.md`): replace the Graphify section and the Graphify
  mentions elsewhere in the file (commit rule, skill routing, plan-formation gate and
  receipt) with a short, tool-neutral statement.
- `README.md`: remove the Graphify section, the skill test command and the sentence about the
  Graphify end-to-end tests, the external-dependency paragraph, and the mentions in the file
  list and the `claude-workflow` description.
- Tests: remove the Graphify cases and the fake-`graphify` docstring text from
  `tests/test_claude_workflow_review.py`; replace the
  `graph-*` strings used only as examples in `tests/test_codex_approver_engine.py` and
  `tests/test_agent_guard_review.py` with other values; drop the one test that reads
  `agents/graphify-semantic.md`.
- ADR 0005: add a dated note that the post-commit graph step no longer exists.

## Non-goals

- `hooks/review_agent_guard.py` stays whole, including its `chunk` mode. The template's
  `graphify-semantic` agent still runs `review_agent_guard.py chunk` from this
  configuration (verified in `modules/graphify/harness/claude/agents/graphify-semantic.md`),
  and the chunk tests in `tests/test_agent_guard_review.py` stay.
- No change to the template, to `ask-codex` or `remote-runner`, or to any skill other than the
  scoped `graphify-workflow` removal and `architecture-decisions` rewording.
- No automatic Graphify refresh is added anywhere (template ADR 0004, decision 5).
- Deleting the `~/.claude` copies: `install.py` never removes, and `rm` is denied, so the
  owner removes them (see Risks).

## Assumptions and constraints

- Owner direction (2026-10-19): remove the `graph-*` commands and `graph-post-commit`; remove
  the commit helper's Graphify handling; remove the skill and agent with their manifest
  lines and tests; keep `hooks/review_agent_guard.py`; reword the CLAUDE.md Graphify section.
- Template ADR 0004 is Accepted and the template's `graphify` module ships the workflow tool,
  skill and agent, so nothing here is the only copy. The marker file the template detects
  (`global_config: true`) is template roadmap candidate 10, not this plan.
- ADR 0005 is Accepted; its body is not rewritten. The note is a dated addition only, which
  needs the owner's approval of this plan.
- The `commit` result loses its `graphify` field. Its consumers in this repository are the
  `safe-committer` agent text and the tests; the approver reads only the command line.

## Discovery and impact evidence

Graphify: skipped — the graph is missing (`graph_missing`), and a grep of the working tree for
`graphify|graph-` enumerates every affected file: the ones listed in Scope plus archived plans
0003 to 0015 and ADR 0005's accepted-risk text, which are historical records and stay
unchanged except for the ADR note. The template side was read to confirm the agent's guard
dependency.

## Completion criteria

- `grep -rIil --exclude-dir=.git --exclude-dir=.debug 'graphify\|graph-' .` lists only: the
  archived plans, ADR 0005 with its note, `hooks/review_agent_guard.py` and the chunk tests in
  `tests/test_agent_guard_review.py` (intentionally kept), the `graphify-out/` sentence in the
  new `CLAUDE.md` section, and this plan once archived.
- `python3 -B -m unittest discover -s tests` passes; `claude-workflow commit` still commits
  and no longer prints a `graphify` field; `claude-workflow context` still runs.
- `python3 install.py --check` reports a match after the owner removes the `~/.claude` copies.

## Increments

### Increment A — Remove the Graphify commands and handling from the helper, with its tests

Dependencies: None
Affected areas: `bin/claude-workflow`, `tests/test_claude_workflow_review.py`,
`tests/test_codex_approver_engine.py`, `tests/test_agent_guard_review.py`,
`hooks/codex_approver.py`, `settings.json`, `agents/safe-committer.md`

1. Delete the `graph-*` subcommands, their handlers and helpers, the post-commit step in
   `commit`, and the `graphify` key of `context`; simplify `dirty_paths`.
2. Remove the matching `settings.json` allow rules and the approver subcommand words.
3. Remove or replace the tests listed in Scope; reword `safe-committer.md`.
4. Run `python3 -B -m unittest discover -s tests` and a throwaway-repository commit through
   `claude-workflow commit`, checking the result has no `graphify` field.

Completion: the suite passes and the helper's `--help` lists only `commit`, `amend-message`,
`remove`, `context` and `project-id`.

### Increment B — Remove the skill and agent

Dependencies: A
Affected areas: `skills/graphify-workflow/`, `agents/graphify-semantic.md`,
`config-manifest.txt`, `README.md`

1. Preview with `claude-workflow remove … --recursive`, then confirm, for the skill directory
   and the agent file.
2. Remove their manifest lines and the README mentions.
3. Run `python3 install.py --check` and the full suite.

Completion: the paths are gone, the manifest lists no Graphify file, and the suite passes.

### Increment C — Reword the policy

Dependencies: B
Affected areas: `CLAUDE.md`, `skills/architecture-decisions/SKILL.md`,
`docs/decisions/0005-codex-approver-may-allow-commits.md`

1. Replace the Graphify section of `CLAUDE.md` with a neutral statement: graph tooling, where
   a project has it, comes from the project's own module; there is no automatic refresh;
   `graphify-out/` stays rebuildable local state that is never staged. Reword the other
   Graphify mentions (commit rule, routing, plan-formation gate and receipt) so a plan
   records a discovery step or "skipped — reason" without naming a tool or helper command.
2. Reword the two lines in `architecture-decisions/SKILL.md`.
3. Add a dated note to ADR 0005 and keep the index row.
4. Sync with `python3 install.py`, then `python3 install.py --check`.

Completion: no policy file names a removed command; the check reports a match.

## Verification

- `python3 -B -m unittest discover -s tests` after A, B and C.
- A throwaway-repository run of `claude-workflow commit`, `amend-message`, `remove` and
  `context`.
- The grep in Completion criteria.
- `git diff --check`.

## Risks and sensitive actions

- This edits the commit helper and the approver's command table, which gate every commit. The
  change is deletion only; the gate logic and the commit path stay as they are, and the
  tests above pin them. An independent read-only review (`workflow-reviewer`) of the final
  diff is part of Increment A's evidence.
- `~/.claude` copies of `skills/graphify-workflow` and `agents/graphify-semantic.md` remain
  until the owner removes them with `! rm -r ~/.claude/skills/graphify-workflow
  ~/.claude/agents/graphify-semantic.md`. Until then, projects with the template's module
  would load two copies, and the deleted-helper commands would be gone but still advertised.
- A project that relied on `claude-workflow graph-*` or on the automatic post-commit refresh
  loses them; the template module's `tools/graphify/workflow.py` replaces the commands, and
  nothing replaces the automatic refresh by design. The owner confirmed no existing project
  needs migration for the earlier modules; this one is unchecked.
- Commits and the push need the owner's approval per increment as usual.

## Deferred work

- A marker file for the template's `global_config` dependency (template candidate 10).
- Whether to drop `hooks/review_agent_guard.py` `chunk` mode later, if the template ships its
  own guard.

## Result

Completed 2026-10-19 in three commits after `0d346d6` (the approved plan):

- **A, `6373617`:** `claude-workflow` lost the 14 `graph-*` commands, their helpers, the
  post-commit Graphify step in `commit` and the `graphify` field of `commit` and `context`.
  `settings.json` lost its 11 `graph-*` allow rules, the approver's `claude-workflow`
  subcommand set lost three graph words, `safe-committer.md` lost two sentences, and the
  Graphify tests were removed or reworded.
- **B, `7cf9ab0`:** `skills/graphify-workflow/` (9 files with its tests) and
  `agents/graphify-semantic.md` were removed with their manifest lines and the README's
  Graphify section; the same commit restored a comment above `EXEC_KEY` and blank lines in the
  tests that an independent review found missing.
- **C, `4c4bb57`:** the `CLAUDE.md` Graphify section became a short tool-neutral
  "Discovery and impact analysis" section; `architecture-decisions` and ADR 0005 (dated note)
  were updated; `python3 install.py` synced `~/.claude`.

Verification: the full suite (`python3 -B -m unittest discover -s tests`) passed after each
increment (934 tests, 5 skipped); `python3 install.py --check` reports a match; the grep in
the completion criteria lists only the intended references. An independent read-only
`workflow-reviewer` pass found no blocking defects and three low findings: two fixed, and
one (the chunk-hook wiring test) left removed because its agent file was deleted in B. The
review also noted that `context` now lists untracked `graphify-out/` files as dirty, which
is intended. Its one full-suite error (an `OSError` in remote-runner test cleanup) did not
reproduce in three full runs here.

Not done here, by design: the `~/.claude` copies of `skills/graphify-workflow` and
`agents/graphify-semantic.md`, and eleven `claude-workflow graph-*` allow rules that remain
in the live `settings.json` as local-only entries, are the owner's to remove.
`hooks/review_agent_guard.py` and its `chunk` mode stay because the template's agent uses
them. The Codex plan review stopped at its bound with all three round-3 findings applied
and not re-reviewed.

### Codex plan review

## Codex plan review

- Plan: docs/plans/next.md (key 4ade000efe363063)
- Rounds used: 3 of 3
- Round 1: model gpt-5.6-luna, effort low, 1 finding(s) (1 blocker or major), 99409 input and 1660 output tokens
- Round 2: model gpt-5.6-luna, effort low, 0 finding(s) (0 blocker or major), 166611 input and 1360 output tokens
- Round 3: model gpt-5.6-luna, effort high, 3 finding(s) (1 blocker or major), 1150266 input and 14460 output tokens
- Outcome: not converged (1 blocker or major finding(s) in the last round)
- Effort raised to high for round 3: round 3 reached (round 3 of this review window)
- Decisions: 2 applied, 0 rejected
