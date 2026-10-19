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
| [0006](0006-codex-approver-evidence-and-report-accuracy.md) | Completed | Approver evidence for `git push`, `remote-runner` and `ask-codex archive`; unmatched-prompt log; fewer false secret declines; accurate verdict/outcome pairing; local host-eligibility facts; advice-only, no allow authority; fetch/cancel fixture-tested only |
| [0007](0007-codex-approver-commit-delegation.md) | Completed | The Codex approver may allow `claude-workflow commit` and nothing else: helper hardening, `delegate` config with a code ceiling, delegated-allow report, ADR 0005, independent security review; live allow observed |
| [0008](0008-document-review.md) | Completed | `ask-codex` and `second-opinion` review specs and roadmaps with the same bounded loop: `review-spec`/`review-roadmap`, new kinds, approver and permission rules, template guidance; path-handling security review and independent review; two real Codex rounds |
| [0009](0009-codex-approver-archive-delegation.md) | Completed | The Codex approver may also allow `ask-codex archive`: `DELEGABLE` ceiling widened, shipped `delegate` list, end-to-end tests, ADR 0006, independent review; live allow observed on a throwaway spec review |
| [0010](0010-commit-decline-noise.md) | Completed | Commit-decline noise: subject guidance, and a hook-computed `reviewer_facing_paths` fact that excuses reviewer-addressed text in review prompt files only; ADR 0007; independent review fixed a `..` bypass; live check not run |
| [0011](0011-adr-review.md) | Completed | `ask-codex` and `second-opinion` review ADRs: `review-adr`/`--adr`, `adr-review` kind, `review-adr` allowed and `archive --adr` accepted by the approver rule; independent review clean; live Codex check skipped |
| [0012](0012-knowledge-base-skills-spec.md) | Completed | Knowledge-base skills specification (Approved) and ADR 0008 (Accepted): two skills, manifest-based store discovery, thin wrappers; four spec review rounds, ADR review clean; no skill built yet |
| [0013](0013-consuming-knowledge-base-skill.md) | Completed | The `knowledge-base` skill: read-only discovery of registered stores, claim tags, path-checked reads; live check with hostile fixtures found and fixed a symlink read; independent review, nine findings applied; spec amended |
| [0014](0014-knowledge-base-authoring-skill.md) | Completed | The `knowledge-base-authoring` skill, create and upgrade a store: dry-run first, path-checked reads, tool-import check, installer output as data; twelve fresh-agent live runs with hostile fixtures; independent and security reviews (thirteen findings applied); four Codex plan-review rounds |
| [0015](0015-knowledge-base-domain-operation.md) | Completed | The `knowledge-base-authoring` skill, create a domain and set its charter: pre-shell allow-list for name and title, separate confirmation before `charter: set`, mechanical tools-import comparison; three rounds of fresh-agent live runs with hostile fixtures; independent and security reviews (findings applied or rejected with reasons); three Codex plan-review rounds |
| [0016](0016-remove-graphify-tooling.md) | Completed | Graphify tooling removed from the global configuration (the template's `graphify` module ships it): 14 `graph-*` commands and the post-commit step gone from `claude-workflow`, the skill and agent removed, `CLAUDE.md` Graphify section replaced by tool-neutral guidance, ADR 0005 noted; guard `chunk` mode kept; independent review, two of three low findings fixed; three Codex plan-review rounds |
