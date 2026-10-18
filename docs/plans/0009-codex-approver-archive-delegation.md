# 0009: Delegate `ask-codex archive` to the Codex approver

Status: Completed
Created: 2026-10-18
Completed: 2026-10-18

## Goal

The Codex approver may allow `ask-codex archive` prompts without a dialog, in
the same way it allows `claude-workflow commit` today: an approved verdict for
that rule prints the single fixed allow decision, and every other result leaves
the normal prompt.

## Scope

- `hooks/codex_approver.py`: add `ask-codex-archive` to the `DELEGABLE` ceiling.
- `codex-approver/config.json`: add the rule to `delegate` (repo mirror and
  `~/.claude` through `install.py`).
- New ADR 0006 widening ADR 0005's ceiling to exactly these two rules; amend the
  ADR 0004 and 0005 headers and the ADR index.
- `docs/specs/codex-approver.md` (Delegation section) and `README.md` (the
  approver's Settings bullet) so both name the two delegable rules.
- Tests that pin the ceiling and the shipped config
  (`test_codex_approver_engine.py`, `test_codex_approver_wiring.py`,
  `test_codex_approver_codex.py`).
- `codex-approver/rubric.md`: the archive section's sentence that the owner
  "asks for it knowingly" no longer holds under delegation; reword it.

## Non-goals

- Delegating `git-push`, `claude-workflow-remove`, `remote-runner-*`, or
  `ask-codex prune`.
- Changing the archive rule's checks, the archive collector, or
  `bin/ask-codex`.
- Tuning the `no_secret_lines` or `facts_complete` false positives.
- Any change to the commit delegation.

## Assumptions and constraints

- Verified in `hooks/codex_approver.py`: `delegated_decision` and
  `load_config` consult only `DELEGABLE`, `mode`, and the `delegate` list, not
  the rule id by name, so the ceiling edit is the only code change.
- Verified in `bin/ask-codex`: `command_archive` only sets the review's
  `closed` state and renders the ledger. It deletes nothing and makes no Codex
  call.
- Evidence (`codex_approver.py --report`, 2026-10-18): `ask-codex-archive` has 8
  approves, all ran, and 1 decline, which was correct (two findings were
  undecided). The sample is small.
- ADR 0005: widening the ceiling is a code change and a new ADR. Needs
  explicit owner approval of this plan before implementation.
- Open decision for the owner: archiving a spec or roadmap review at its round
  bound is how more rounds are opened. Delegation lets Codex approve that
  without the owner. Proposed: accept it, because the extra rounds are
  read-only, advisory, and cost only Codex calls. Alternative: leave this
  rule's authority to `--plan` archives only (a deterministic check in the
  collector, a larger change).

## Discovery and impact evidence

Graphify: skipped — scope fully enumerated by `grep DELEGABLE` over the
repository (one definition, one use in `load_config`, one in
`delegated_decision`, one pinning test) and ADR 0005's list of delegation
surfaces.

## Completion criteria

- The full approver test suite passes, including new tests showing an approved
  delegated archive prints exactly the allow decision and a declined or
  no-verdict archive prints nothing.
- A config naming any rule other than the two delegable ones is still a config
  error.
- ADR 0006 is Accepted, the specs and README name both rules, and
  `git diff --check` is clean.
- `~/.claude` is synced from the repository.

## Increments

### Increment A — Delegate `ask-codex-archive`

Dependencies: None
Affected areas: `hooks/codex_approver.py`, `codex-approver/config.json`,
`codex-approver/rubric.md`, `docs/decisions/`, `docs/specs/codex-approver.md`,
`README.md`, `tests/test_codex_approver_*.py`

1. Write the failing tests: the ceiling equals both rule ids; the shipped
   config delegates both; an approved `ask-codex archive` prints the allow
   decision after its row is logged (`decision: allow`); decline, no verdict,
   a hung Codex, and a failed deterministic check print nothing; `git-push`
   in `delegate` is still a config error.
2. Add the rule id to `DELEGABLE` and to `config.json`'s `delegate`; update
   the comment above `DELEGABLE`.
3. Reword the archive rubric sentence and run the rubric tests.
4. Write ADR 0006 (Accepted after approval), amend the ADR 0004 and 0005
   status lines, update the index, the spec, and the README.
5. Sync to `~/.claude` with `install.py` and run the full test suite and
   `git diff --check`.
6. Live check: one `ask-codex archive` on a finished review runs without a
   dialog and its verdict row says `decision: allow`; `--report` lists it under
   delegated allows.

Completion: tests pass; the live check's verdict row and outcome row exist;
the diff touches only the listed files.

## Verification

- The repository's approver tests (`tests/test_codex_approver_*.py`) through
  the documented test command, run before and after the change.
- `python3 ~/.claude/hooks/codex_approver.py --report` after the live check.
- `git diff --check`.

## Risks and sensitive actions

- Widens the approver's authority, which is security-relevant, so the
  change warrants an independent review (`workflow-reviewer`) before the
  commit.
- An archive cannot be undone for a plan review. Codex's `review_is_finished`
  check is the only guard against closing with undecided findings, and a
  decline still falls back to the normal prompt.
- The live check closes a real review; use a throwaway one.
- Edits `~/.claude`, which only `install.py` should do.

## Result

`ask-codex-archive` joined `claude-workflow-commit` on the `DELEGABLE` ceiling and in the shipped `delegate` list
(ADR 0006, Accepted). The owner approved the plan and the open decision (accept that Codex may approve an archive that
opens a fresh bound for a spec or roadmap) on 2026-10-18. Graphify: skipped, as recorded above.

- Tests: red first (the ceiling, config validation, the shipped config and `delegated_decision`), then green. Five
  end-to-end hook tests (`DelegatedArchiveTests`) cover an approved archive printing exactly the allow line, a decline
  and a Codex failure, advice mode, a commit-only list, and a failed deterministic check. Removing the rule from
  `DELEGABLE` failed 7 of the archive tests. Final suite: 907 tests, 5 skipped; `git diff --check` clean;
  `install.py --check` reports no drift.
- Independent read-only review (`workflow-reviewer`): no functional or security defect. Its stale-wording findings
  (spec authority row, the advice-only paragraph, the archive flag list, the ADR 0005 index title, two test comments)
  and its missing end-to-end archive tests were fixed.
- Live check (2026-10-18, throwaway spec `docs/specs/zz-live-check.md`, removed afterwards): `ask-codex review-spec
  --max-rounds 1` ran one real Codex round; both major findings were recorded as rejected; `ask-codex archive --spec`
  then ran with no dialog. The verdict row reads `rule: ask-codex-archive`, `verdict: approve`, `mode: delegate`,
  `decision: allow`, and the outcome row `ran`, exit 0. `--report` lists it under delegated allows (1).
- Not observed: a live decline of an archive. It is covered by the end-to-end tests only.

Residual: the sample behind the delegation is small (8 approves, 1 correct decline before this plan). Codex sees only
counts and ids from `ask-codex status`, not the findings, so `review_is_finished` is the sole guard against closing a
plan review early. The throwaway review's state remains under the git-excluded `.debug/2026-10-18-spec-review/`.
