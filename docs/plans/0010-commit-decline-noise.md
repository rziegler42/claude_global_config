# 0010: Commit-decline noise: subject guidance and reviewer-facing paths

Status: Completed
Created: 2026-10-18
Completed: 2026-10-18

## Goal

Cut the commit declines that are noise, without widening what the Codex approver
may allow: (1) commit subjects describe only what the commit contains, and (2)
a commit that edits reviewer-facing prompt files is no longer declined for
`no_reviewer_directed_text` merely because those files address a reviewer.

## Scope

Increment A, guidance (no behavior change):

- `agents/safe-committer.md` and the commit bullet in `CLAUDE.md` (repo root and
  the mirrored `~/.claude/CLAUDE.md`): the subject names only changes present in
  the staged diff of the listed paths. A path already identical to `HEAD`
  (for example an already-empty `next.md`) is not mentioned.

Increment B, rubric exemption:

- `hooks/codex_approver.py`: the commit collector adds a fact
  `reviewer_facing_paths`, computed by the hook (never by Codex) as the
  requested paths that match a fixed list in code.
- `codex-approver/rubric.md`: a rule for `no_reviewer_directed_text` in the
  commit section, applying only to paths listed in `reviewer_facing_paths`.
- `docs/specs/codex-approver.md`, an ADR (0007), and the ADR index.
- Tests: the collector fact, the fixed list, and the shipped rubric wording
  (hostile fixtures included).

## Non-goals

- Delegating any further rule, or changing `DELEGABLE`.
- Exempting `codex-approver/rubric.md`, `codex-approver/rules/`,
  `codex-approver/config.json` or `hooks/codex_approver.py`. A commit that
  changes the approver's own policy keeps going to the owner (see the 14:09
  decline of the ADR 0006 commit, which was correct).
- Tuning `no_secret_lines`, `facts_complete`, or `head_matches`.
- Changing other rules' `no_reviewer_directed_text` checks.

## Assumptions and constraints

- Evidence (verdict log, 2026-10-17 to 2026-10-18): 15 commit declines against
  28 approves. Two were `message_matches_change` on subjects claiming a
  `next.md` reset that was not in the diff (correct declines, caused by
  wording). Two were `no_reviewer_directed_text` on `ask-codex/kinds/*/prompt.md`
  and `codex-approver/rubric.md`, which exist to instruct a reviewer.
- Open decision for the owner: which paths count as reviewer-facing. Proposed
  fixed list: `ask-codex/kinds/*/prompt.md`, `skills/second-opinion/**`,
  `agents/workflow-reviewer.md`, `agents/security-reviewer.md`.
  `codex-approver/rubric.md` is deliberately excluded, per Non-goals.
- Security shape: the exemption is a fact computed in code from the path list,
  so file content or the commit message cannot claim it. Inside an exempt path,
  text that addresses a reviewer as part of the file's job passes. Text that
  tries to influence this review (states a verdict to give, claims the change
  is pre-approved or already reviewed, poses as a system message, or targets
  the FACTS block) still fails, as does the same text in the subject, body, a
  non-exempt path, or a path name. `change_is_safe_in_itself` is unchanged, so
  weakening a review prompt's checks still fails.
- Accepted risk to record in the ADR: a malicious edit hidden in an exempt
  prompt file relies on Codex's other checks and the owner's later push review
  (`git-push` is not delegated).
- Subject wording is guidance only; nothing enforces it.

## Discovery and impact evidence

Graphify: skipped — the touched files are enumerated above and the change is
confined to one hook collector, one rubric section and their tests; precedent is
ADR 0005/0006 and plan 0009.

## Completion criteria

- Guidance text is present in `agents/safe-committer.md`, repo `CLAUDE.md`, and
  `~/.claude`, with `install.py --check` clean.
- A commit touching only exempt prompt files, with an honest message, is
  approved by the fake Codex path in tests; the same text in a non-exempt path
  or in the subject still fails `no_reviewer_directed_text`.
- A hostile fixture inside an exempt path that tries to steer the review still
  declines.
- Full suite and `git diff --check` pass.

## Increments

### Increment A — Subject guidance

Dependencies: None
Affected areas: `agents/safe-committer.md`, `CLAUDE.md`

1. Add one sentence to the commit guidance in both files.
2. Run the existing wiring tests that pin these files, then `install.py --check`.

Completion: guidance mirrored; no test regression.

### Increment B — Reviewer-facing path exemption

Dependencies: owner confirms the path list; Increment A is independent.
Affected areas: `hooks/codex_approver.py`, `codex-approver/rubric.md`,
`docs/specs/codex-approver.md`, `docs/decisions/0007-*.md`,
`docs/decisions/README.md`, `tests/test_codex_approver_*.py`

1. Write failing tests for the collector fact and rubric wording.
2. Add the fixed list and fact; add the rubric rule.
3. ADR 0007, spec and index updates.
4. Independent review, then a live check with a prompt-file commit.

Completion: tests green; live verdict row shows the fact and an approve.

## Verification

`python3 -B -m unittest discover -s tests -p 'test_codex_approver*.py'`, the
full suite, `git diff --check`, `python3 install.py --check`, and a
`workflow-reviewer` pass on Increment B.

## Risks and sensitive actions

Increment B edits the approver's rubric and hook, which govern what is allowed
without a prompt. It must not alter `DELEGABLE` or the output shape. Commits of
this plan's files will themselves touch `rubric.md` and are expected to prompt.

## Deferred work

The secret-scan and `facts_complete` false positives; stale-`--expected-head`
declines from other sessions.

## Result

Increment A: subject guidance added to `CLAUDE.md` and `agents/safe-committer.md`. Increment B: `reviewer_facing_paths`
fact (`is_reviewer_facing`, segment-by-segment on a canonical path), commit rubric exception, ADR 0007, spec note, tests
(`ReviewerFacingPathTests`).

Verification: full suite 913 tests, 5 skipped, 0 failed; `git diff --check` clean; `install.py --check` no drift.
An independent `workflow-reviewer` pass found that `..` segments and a `*` crossing `/` could widen the list to the
approver's own policy files; both were fixed and regression-tested. Its note that agent frontmatter permissions are not
excused was added to the rubric and ADR.

Not done: the live check (an approved commit of a listed prompt file) was not run; the first such commit will show
`reviewer_facing_paths` in the verdict log. The reviewer did not re-review after the fix, and could run no experiments.

Residual risk: a harmful edit inside a listed prompt file relies on `change_is_safe_in_itself` and the owner's push review.
