# 0006: The Codex approver may also allow `ask-codex archive`

Status: Accepted
Date: 2026-10-18

## Context

ADR 0005 let the approver allow `claude-workflow commit` and named widening the ceiling as a code change plus a new
ADR. The approver's report (`codex_approver.py --report`, 2026-10-18) shows `ask-codex-archive` with 8 approves, all
of which ran (the owner never refused an approve), and 1 decline, which was correct: two findings were undecided.
The sample is small. `ask-codex archive` only sets the review's `closed` state and renders its ledger; it deletes
nothing and makes no Codex call. For a plan review the close is permanent.

## Decision

`DELEGABLE` in `hooks/codex_approver.py` becomes `{claude-workflow-commit, ask-codex-archive}`, and the shipped
`delegate` list names both. Every other term of ADR 0005 applies to the archive rule unchanged: the ceiling is code,
the only output is the one fixed allow line printed after the verdict row is logged, and a decline, no verdict,
timeout, outage or configuration error leaves the normal prompt.

## Alternatives considered

- **Delegate archive for `--plan` only.** Rejected: it needs a new deterministic check in the collector for little
  protection, since the extra rounds below are advisory.
- **Delegate `git-push`, `claude-workflow-remove` or `remote-runner-*` too.** Not adopted. Push is outward-facing,
  remove deletes files, and the owner overrode Codex's declines on both; submit declines mostly because Codex cannot
  see the profile script.

## Consequences

- An archive Codex approves runs with no dialog and about 5 to 10 seconds of delay.
- **Accepted risk: more rounds without the owner.** Archiving a spec or roadmap review at its round bound opens a
  fresh bound, so Codex's approval can let the assistant run more rounds than the owner chose. The rounds are
  read-only and advisory and cost only Codex calls.
- **Accepted risk: a premature plan close.** `review_is_finished` is the only guard against closing a plan review
  with undecided findings, and a plan review cannot be reopened. Codex sees only counts and ids from
  `ask-codex status`, not the findings.
- The rule file, like the config, is trusted owner-controlled data (see ADR 0005).

## Verification

`tests/test_codex_approver_engine.py` (the ceiling and config validation), `test_codex_approver_codex.py`
(`DecisionFunctionTests`), `test_codex_approver_wiring.py` (the shipped config), and a live `ask-codex archive` on a
throwaway review whose verdict row carries `decision: allow`. Results are in plan 0009.

## Related files and decisions

- `docs/decisions/0004-codex-approver-advice-only.md`, `docs/decisions/0005-codex-approver-may-allow-commits.md`
- `docs/specs/codex-approver.md`
- `hooks/codex_approver.py`, `codex-approver/rules/ask-codex-archive.json`, `codex-approver/rubric.md`
