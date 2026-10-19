# 0005: The Codex approver may allow `claude-workflow commit`, and nothing else

Status: Accepted
Date: 2026-10-17
Widened by ADR 0006: `ask-codex archive` joins the ceiling; the rest of this record stands.
Note 2026-10-19: `claude-workflow commit` no longer runs a post-commit Graphify step (plan 0016), so the
"post-commit graph step" accepted risk below is moot; the rest of this record stands.

## Context

ADR 0004 shipped the Codex approver advice-only and left `allow` as "a separate decision". The evidence
period it asked for has produced a measured record: of the 37 verdicts logged by 2026-10-17, 28 were
`claude-workflow commit` approves and every one ran (the owner never refused an approve), while four commit
declines were overridden by the owner (three early secret-check declines and one scope judgement). The owner is the only user of this workflow, so the realistic risks are a mistaken or
misled assistant, hostile repository content, and a wrong approval, not a remote attacker.

Plan 0005 and ADR 0004 named four prerequisites before any `allow`: harden the real helper (it ran Git without
the hook's protections), settle the secret-detection question, close the gap between approval and execution,
and show that a slow Codex cannot produce a late allow. Plan 0007
(`docs/plans/0007-codex-approver-commit-delegation.md`) delivered the first three; the late-allow check is covered by
tests for a hung Codex and by the fact that a killed hook's output is discarded, not by a live observation.

## Decision

The approver may print an `allow` decision for **`claude-workflow commit` prompts only**, when every deterministic
check passed and Codex approved. The owner remains the backup: in every other case nothing is printed and the
normal prompt appears.

- **Ceiling in code.** `DELEGABLE` in `hooks/codex_approver.py` names the only rule that can be delegated.
  `delegate` in `codex-approver/config.json` selects among those and can never add to them. A config that names
  anything else is a config error, which disables the hook's output. Widening the ceiling is a code change and a
  new ADR.
- **Explicit mode.** `mode` is `advise` (the shipped value; `delegate` must be empty) or `delegate` (needs a
  non-empty list). Setting it back to `advise` and syncing revokes the authority.
- **One fixed output.** The only thing the hook ever prints is
  `{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}`, and only after
  the verdict row, carrying `decision: allow`, has been written. A failed log write prints nothing.
- **No verdict is no decision.** A decline, no verdict, timeout, Codex outage, malformed reply, configuration
  error or any other rule prints nothing. Codex can only confirm or veto what the gate passed and cannot promote
  a declined command.
- **The helper enforces the gate at execution time.** `claude-workflow commit` now refuses a repository that
  selects programs the commit would run (hooks, filter drivers, a signing, diff or ssh program, fsmonitor), unless
  the owner passes `--allow-repo-programs`, which the approver's rule does not accept. It runs Git with
  `GIT_NO_REPLACE_OBJECTS=1`. A parity test keeps the helper's check and the gate's check naming the same
  settings. A repository changed after approval, a moved `HEAD` or newly staged work is refused by the helper.
- **Reporting.** `--report` counts delegated allows separately from the advice figures, because the owner judged
  nothing about them. It shows how many ran, ran and failed, or left no outcome.

## Alternatives considered

- **Delegate commit and remove together (the original increment 2).** Rejected for now: `remove` deletes files
  and has had one live verdict. It can follow with its own evidence and ADR.
- **Let the config choose any rule.** Rejected: one edit to a data file could then hand `git push` to a model. The
  ceiling is code so that widening it is reviewed.
- **Treat a delegated allow as agreement.** Rejected: it would inflate the figure that justifies delegation.
- **A stricter secret scan before delegating.** Not adopted (owner decision, 2026-10-17); see Consequences.
- **Disable repository hooks in the helper instead of refusing.** Rejected: it would silently skip a hook a
  repository relies on. Refusing with an explicit owner opt-in is visible.

## Consequences

- A commit the approver approves is made with no dialog and about 5 to 10 seconds of delay for the Codex call. A
  prompt the owner answers first simply uses the owner's answer.
- **Accepted risk: secret detection is heuristic.** A secret that evades it can be committed locally without a
  prompt. It cannot leave the machine without `git push`, which stays with the owner and has no authority here.
  The recorded safeguards are the credential-name check, the pattern and entropy scan, and Codex's review.
- **Accepted risk: Codex can be wrong or manipulated** through commit-message or file content. The deterministic
  gate and the helper's own checks do not depend on it, but a coherent-looking wrong commit can still be approved.
  It stays local and recoverable until pushed.
- **Accepted risk: the post-commit graph step.** After a commit the helper runs the installed `graphify` (found on
  the helper's trusted `PATH`) over the repository when a graph exists. It acts on repository data, not on a program
  the repository chooses, and it ran after every commit before this ADR. It is not part of the gate; the independent
  review could not test it, and a stricter policy would be a separate decision.
- **Accepted risk: the rule and config files are trusted.** The ceiling is keyed on the rule id, so a rule file edited
  to keep the id but drop its checks would still be delegable, and a duplicate key in `config.json` resolves
  last-wins. Both files, like the hook itself, are owner-controlled code and data under `~/.claude`.
- **Gap between approval and execution** remains narrow, not zero: the helper rechecks `HEAD`, the index,
  paths and repository programs when it runs.
- If the exact decision JSON were not honored by Claude Code, the result is the normal prompt (fail-safe). The
  live check records that it is honored.
- Behavior was observed on macOS and Claude Code 2.1.301 only; the hook output shape is checked live in
  plan 0007 increment E.

## Verification

`tests/test_codex_approver_codex.py` (`DelegationTests`, `DecisionFunctionTests`, including a log-write failure and a
hung Codex), `tests/test_codex_approver_engine.py` (config validation and the ceiling),
`tests/test_codex_approver_outcomes.py` (`DelegatedReportTests`), `tests/test_commit_helper.py`
(`RepositoryPrograms`), `tests/test_codex_approver_tools.py` (`HelperParityTests`, the rule rejects the opt-in
flag), mutation checks of the delegation tests, an independent adversarial security review, and a live check in
`auto` mode of one allowed and one declined commit. Results are in the plan's Result section.

## Related files and decisions

- `docs/decisions/0004-codex-approver-advice-only.md` (amended for the commit rule only)
- `docs/specs/codex-approver.md`
- `hooks/codex_approver.py`, `bin/claude-workflow`, `codex-approver/`
