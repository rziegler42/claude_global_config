---
name: architecture-decisions
description: Use when a durable design choice needs an ADR, or when asked to propose, record, accept, reject, refine, or supersede a repository ADR.
---

# Architecture decisions

Use this for durable design constraints, not routine implementation details.

1. Read repository guidance and find the existing ADR convention: location, numbering, header format, status lifecycle, index, and related accepted decisions. The repository's conventions override this skill's defaults. Otherwise use `docs/decisions/` and four-digit sequential names.
2. Inspect only evidence needed for the decision. Graphify and memory are discovery aids, never authority. Cite living sources (architecture documents, tables, plans) instead of duplicating them in the ADR.
3. For a proposal, present context, recommendation, alternatives, consequences, and verification, then wait for explicit approval before writing or accepting it. A request to record an already-made decision is approval to write it, not to accept it; likewise an explicit request for a specific clarification of a `Proposed` ADR is approval to write that refinement, never to accept the ADR.
4. Assign only a status the repository's lifecycle allows, and mark an ADR `Accepted` only when that lifecycle's acceptance conditions are met and the user explicitly approves. If acceptance requires implementation evidence plus user approval, record an approved but unimplemented decision as `Proposed`. Never mark an ADR `Accepted` merely because its design was approved. Record the acceptance evidence, and any explicitly approved waiver of an acceptance item, in the ADR in the same edit, because accepted records are not edited afterward.
5. Use the next unused number; never reuse, renumber, or fill gaps.
6. Create or edit one ADR while preserving conventions and unrelated work. Never rewrite accepted history to hide a changed choice. To change an accepted decision, supersede it with a new ADR that links back to the old one, and change only the old ADR's status line to name its successor, leaving its body unchanged. Mark the old ADR `Superseded` only when its successor is `Accepted`; until then the old decision stands. While an ADR is still `Proposed`, a repository's dated-refinement convention may record reviewed changes that do not change the decision. Once `Accepted`, a narrow clarification needs explicit user approval and is recorded as a dated note (for example a dated refinement) with the accepted body left unchanged; a changed decision needs a superseding ADR.
7. Update an existing ADR index when present, including its status text, and run the repository's ADR or index consistency check if one exists. Look for Makefile targets or scripts named for `adr`, `decision`, or status checks, and in the development docs. Such a check typically compares only the ADR's leading status word with its index row, so keep the two in agreement. It usually does not scan prose, so after a status change still search for references to the old status: update living documents, and flag references in other accepted ADRs instead of editing them. Also run any tests or checks the development docs select for the changed ADR, including tests that read ADR text.
8. Do not implement follow-up work unless requested. Recommend a Graphify semantic refresh when the project graph should include the changed ADR.

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

A repository's own status set wins (for example `Partially superseded`, or a dated note after the status word). `Date:` is when the ADR was written; put acceptance and revision dates in the status note. Flag contradictions found inside an ADR instead of rewriting earlier text. Keep rationale specific and consequences honest. Never copy ADR bodies into memory.
