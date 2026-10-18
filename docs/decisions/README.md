# Architecture decisions

Record durable design choices here as Architecture Decision Records (ADRs).
ADRs explain why a decision was made; current architecture documents describe
the resulting system.

## Status and lifecycle

- **Proposed** — under review; not yet a project decision.
- **Accepted** — explicitly approved design decision. Implementation may
  follow in a separate plan.
- **Rejected** — considered but explicitly not adopted.
- **Superseded** — replaced by a newer ADR, which links back to this record.

Do not rewrite an accepted ADR to change a decision. Create a new ADR that
supersedes it. Record implementation evidence in the ADR's verification section
and in the associated implementation plan.

## Naming and format

- Use the next unused four-digit number: `0001-short-title.md`.
- Do not reuse, renumber, or fill gaps in ADR numbers.
- Keep each ADR concise: context, decision, alternatives, consequences,
  verification, and related files and decisions.

```markdown
# NNNN: Decision title

Status: Proposed | Accepted | Rejected | Superseded by ADR NNNN
Date: YYYY-MM-DD

## Context
## Decision
## Alternatives considered
## Consequences
## Verification
## Related files and decisions
```

## Index

List every ADR, including rejected and superseded records.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-codex-reviews-with-a-prompt-only-read-boundary.md) | Codex plan review runs read-only with a prompt-only read boundary | Accepted |
| [0002](0002-snapshot-bundle-submission.md) | Test uncommitted work by submitting a snapshot bundle | Accepted |
| [0003](0003-remote-runner-fetch.md) | Retrieve job output with a framed fetch over the worker channel | Accepted |
| [0004](0004-codex-approver-advice-only.md) | A Codex approver for trusted helper prompts, advice-only first | Accepted |
| [0005](0005-codex-approver-may-allow-commits.md) | The Codex approver may allow `claude-workflow commit`, and nothing else (originally; widened by 0006) | Accepted |
| [0006](0006-codex-approver-may-allow-archive.md) | The Codex approver may also allow `ask-codex archive` | Accepted |
| [0007](0007-reviewer-facing-paths-in-commit-review.md) | Commit review excuses reviewer-addressed text in a fixed list of reviewer-facing files | Accepted |
| [0008](0008-knowledge-base-skills-are-thin-wrappers.md) | Knowledge-base skills are thin wrappers that discover stores from the manifest | Proposed |
