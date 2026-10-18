# 0007: Commit review excuses reviewer-addressed text in a fixed list of reviewer-facing files

Status: Accepted
Date: 2026-10-18

## Context

The commit rule's `no_reviewer_directed_text` check fails any text that addresses a reviewer. Files that exist to
instruct a reviewer (review prompts, the second-opinion skill) are made of such text. Commits to them were declined
(2026-10-18, `ask-codex/kinds/*/prompt.md`) and the owner overrode every one. The ceiling in ADR 0005 and 0006 is
unchanged by this record.

## Decision

- The hook computes `reviewer_facing_paths`: the requested commit paths matching `REVIEWER_FACING_PATHS` in
  `hooks/codex_approver.py` (`ask-codex/kinds/*/prompt.md`, `skills/second-opinion/*`, `agents/workflow-reviewer.md`,
  `agents/security-reviewer.md`). The commit message, file content and Codex cannot add to it.
- `codex-approver/rubric.md` (commit section only) excuses text aimed at a reviewer of that file's own document, in
  those paths only. Text trying to influence this review (stating the verdict, claiming pre-approval, posing as a
  system message, addressing the FACTS block) still fails, anywhere. `change_is_safe_in_itself` is unchanged.
- Matching is segment by segment on a canonical path: `*` never crosses `/`, and a path with `.`, `..` or empty
  segments is never listed. Tool or permission changes in an agent file's frontmatter are not excused.
- **Not listed, on purpose:** `codex-approver/` (rubric, rules, config) and `hooks/codex_approver.py`. A commit that
  changes the approver's own policy keeps going to the owner.

## Alternatives considered

- Exempt everything under `codex-approver/` too. Rejected: the approver would help approve edits to itself.
- Let Codex judge whether a file is reviewer-facing. Rejected: the commit could argue the point.
- Leave the declines. Rejected: each costs a manual override, which dilutes the agreement figure.

## Consequences

- **Accepted risk:** a harmful edit inside a listed prompt file (for example one that quietly weakens a review) relies
  on Codex's `change_is_safe_in_itself` and the owner's push review (`git-push` is not delegated).
- The list is code; widening it needs a code change and review. Moving or renaming a listed file removes its
  exemption (fail-safe: a prompt).

## Verification

`tests/test_codex_approver_codex.py` (`ReviewerFacingPathTests`), the full suite, and a live commit of a prompt file.

## Related

ADR 0004, 0005, 0006; `docs/specs/codex-approver.md`; `codex-approver/rubric.md`.
