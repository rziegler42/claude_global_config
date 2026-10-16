# Implementation plans

Use `next.md` for the single active implementation plan. A plan may contain
multiple ordered increments, but each increment should produce one coherent,
reviewable result. When `next.md` is empty, no plan is active. Keep the plan
short enough for a new session to understand without reconstructing history.
Planning tools and skills may supply a method or content structure, but they do
not override this location. Put the active plan here; durable requirements and
specifications belong in `docs/specs/`. Do not create tool-owned planning or
specification directories.

Begin each plan with its goal, scope, non-goals, assumptions, and whole-plan
completion criteria. Label top-level increments with uppercase letters in
execution order (`Increment A`, `Increment B`, and so on), and number the steps
within each increment starting at 1. Every increment must state its intended
outcome, affected files or components, dependencies, implementation steps,
verification, and observable completion criteria. Call out risky, irreversible,
security-sensitive, or externally visible actions before implementation.

Write a complete plan with `Status: Proposed`, then obtain explicit approval
before changing it to `Approved` or beginning implementation. Use `In Progress`
while implementation is underway.

After a completed plan is fully verified, archive its final state as the next
unused four-digit file. An explicitly superseded plan may be archived without
completion evidence:

```text
docs/plans/0001-short-title.md
docs/plans/0002-next-title.md
```

Do not reuse numbers, renumber files, or fill gaps. Use `Status: Completed` for
verified work and `Status: Superseded` when an explicit decision replaces
unfinished work. Reset `next.md` after archiving.

Archived plans record intended work, verification, and results. They are
historical evidence, not durable architectural authority. Record lasting
design constraints as ADRs under `docs/decisions/`.

Do not collect unapproved plan fragments in ad hoc files under `docs/plans/`.
Keep multi-plan direction in `docs/roadmaps/` instead.

Treat a plan as a draft until it is explicitly approved. Reorder and relabel a
draft cleanly as findings change it. After approval, preserve increment labels
and scope unless a revision is explicitly approved. Classify new findings
before editing the plan: add a step when the existing increment outcome is
unchanged; add an increment for a separately reviewable outcome or prerequisite;
update assumptions, risks, or decisions when no implementation work is added;
and record out-of-scope work as deferred work or in a roadmap. When an approved
plan needs an increment between `B` and `C`, use the next letter-only suffix
(`B-A`, then `B-B`) rather than relabeling existing increments.

Before presenting a plan, check its labels and numbering, dependencies,
verification and completion evidence, unresolved placeholders, risky actions,
unintended scope growth, and any discovery or impact evidence the project
requires.

## Archive format

```markdown
# NNNN: Plan title

Status: Completed | Superseded
Created: YYYY-MM-DD
Completed: YYYY-MM-DD

## Outcome

## Scope

## Non-goals

## Assumptions

## Completion criteria

## Constraints

## Increments

### Increment A — outcome

Dependencies: None
Affected areas: `path/to/file`

1. Implementation step.
2. Verification step.

Completion: Observable evidence.

## Verification

## Deferred work

## Result
```

## Archives

| Plan | Status | Outcome |
|---|---|---|
| [0001](0001-install-py-and-settings-policy.md) | Completed | `install.py` replaces `install.sh`; settings policy, plugin presence, file-mode rules, security hardening |
| [0002](0002-second-opinion-plan-review.md) | Completed | `ask-codex` and the `second-opinion` skill: bounded, read-only Codex plan review; two security reviews; calibration |
| [0003](0003-remote-runner-snapshot-submission.md) | Completed | Security review of the helpers and guard; structural permission set; `remote-runner submit --snapshot` with bundle transport and provenance; ADR 0002; probes and live prune check carried as deferred |
| [0004](0004-remote-runner-fetch.md) | Completed | `remote-runner fetch`: framed, owner-prompted retrieval of job output with `--dest`/`--as`; three independent security-review passes; ADR 0003; live fetch from `ned` verified |
| [0005](0005-codex-approver.md) | Completed | `codex_approver.py` `PermissionRequest` hook: gate-then-Codex advice for `claude-workflow commit`/`remove` prompts; four security-review passes; ADR 0004; model and rubric chosen from measured cost; live check in `auto` mode |
