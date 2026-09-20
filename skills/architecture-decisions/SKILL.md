---
name: architecture-decisions
description: Propose, record, accept, reject, or supersede concise repository ADRs for durable design choices with meaningful alternatives.
---

# Architecture decisions

Use this for durable design constraints, not routine implementation details.

1. Read repository guidance and find the existing ADR convention, index, and related accepted decisions. Otherwise use `docs/decisions/` and four-digit sequential names.
2. Inspect only evidence needed for the decision. Graphify and memory are discovery aids, never authority.
3. For a proposal, present context, recommendation, alternatives, consequences, and verification, then wait for explicit approval before writing or accepting it. A request to record an already-made decision is approval to write it.
4. Create or edit one ADR while preserving conventions and unrelated work. Never rewrite accepted history to hide a changed choice.
5. Supersede by creating a new ADR and cross-linking both records. Update an existing ADR index when present.
6. Do not implement follow-up work unless requested. Recommend a Graphify semantic refresh when the project graph should include the changed ADR.

Default template when the repository has none:

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

Keep rationale specific and consequences honest. Never copy ADR bodies into memory.

