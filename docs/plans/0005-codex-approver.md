# 0005: Codex approver (advice-only)

Status: Completed
Created: 2026-10-16
Completed: 2026-10-16

## Outcome

`hooks/codex_approver.py` is a `PermissionRequest` hook, installed and running. For owner prompts raised by
`claude-workflow commit` and `claude-workflow remove --confirm` it collects trusted facts, runs deterministic
checks, asks Codex to review what the checks cannot, and records a verdict in a local log with a macOS
notification. It prints nothing and never decides, so the owner still answers every prompt. Behavior is defined in
`docs/specs/codex-approver.md` (increment 1 of that specification) and ADR 0004.

## Scope

- `hooks/codex_approver.py` and the `codex-approver/` data directory (`config.json`, `rubric.md`,
  `verdict.schema.json`, `rules/claude-workflow-commit.json`, `rules/claude-workflow-remove.json`).
- `settings.json` hook registration, `config-manifest.txt`, `.gitignore`, README section, ADR 0004, four test files.
- Install and a live check in `auto` mode.
- Added during the work at the owner's direction: a model and effort search by measured cost, the same analysis for
  plan reviews (`ask-codex/config.json`, `docs/specs/second-opinion-plan-review.md`), and security-review fixes
  beyond the original plan.

## Non-goals

- `allow` authority, `CLAUDE.md` policy changes, and rules for other commands (specification increment 2).
- The project registry and hash pin (specification increment 3).
- The next-increment approval gate and the `claude_project_template` module.
- Changes to `claude-workflow` or to existing `ask`/`deny` rules.

## Assumptions

- Claude Code 2.1.301 and macOS; the hook behavior in the specification's Evidence section.
- Rules are JSON and name collectors and checks from fixed registries, so a new command is a rule file plus a
  fixture.
- Any error, timeout, or unexpected input yields empty stdout and exit 0, so the normal prompt appears.

## Completion criteria

- Specification acceptance criteria 1 to 7, 9 and 10 hold (8 belongs to increment 2).
- Full suite passes and `git diff --check` is clean.
- Independent security review passes leave no unresolved Critical or High issue that matters before `allow`.
- A live check in `auto` mode shows an `ask`-tier commit and remove prompt receiving a logged verdict.

## Constraints

- No commit, push, install, or settings change without owner approval; the install was approved on 2026-10-16.
- The Codex Plus allowance is limited; evaluations had to stay inside it (see Result).

## Increments

### Increment A — Measure Codex latency and hook timeout behavior

Dependencies: None
Affected areas: untracked `.debug/` notes only

1. Time `codex exec` with the verdict schema from an empty directory over several models and efforts.
2. Run a nested `claude -p` with a hook that outlives its `timeout`.
3. Choose model, effort and timeouts.

Completion: reviews took 3.7 to 6.5 s; a hook that outlives its timeout is killed and its `allow` is ignored;
Codex needs `--skip-git-repo-check` from a non-git directory. Specification Evidence updated.

### Increment B — Engine core with no Codex

Dependencies: A
Affected areas: `hooks/codex_approver.py`, `codex-approver/config.json`, `tests/test_codex_approver_engine.py`

1. Strict command splitting (raw literal spellings, quote-free executable word) and a tokenizer that refuses
   anything not plainly literal.
2. Rule matching, strict config and rule loading, a private rotating log, a notifier, and a hook entry that never
   prints.

Completion: engine tests pass; malformed and hostile stdin always gives empty stdout and exit 0.

### Increment C — Rules, collectors, deterministic checks

Dependencies: B
Affected areas: `hooks/codex_approver.py`, `codex-approver/rules/*.json`, `tests/test_codex_approver_rules.py`

1. Hardened Git environment; the installed `claude-workflow` is loaded and its validators reused.
2. Commit and remove collectors that compute changes in Python (no Git diff or status against the working tree,
   so repository filters never run).
3. Twelve-plus deterministic checks and an invocation check that emulates the shell's `PATH` lookup.

Completion: rule tests pass, including hostile repository configuration, replace refs, hardlinks, symlinks,
secrets, stale HEAD and `PATH` shadows.

### Increment D — Codex review and verdict

Dependencies: C
Affected areas: `hooks/codex_approver.py`, `codex-approver/rubric.md`, `codex-approver/verdict.schema.json`,
`tests/test_codex_approver_codex.py`

1. Rubric, nonce-delimited one-line facts, a Codex runner (empty temporary directory, read-only, minimal
   environment, process-group kill) and strict reply validation.
2. A deterministic failure declines without calling Codex; only a request that passes every check is reviewed.

Completion: fake-Codex tests cover approve, decline, timeout, outage, bad replies and injection; a live check of
the rubric on the real Codex matched all seven hand-built cases.

### Increment E — Wiring, documentation, ADR

Dependencies: D
Affected areas: `settings.json`, `config-manifest.txt`, `.gitignore`, `README.md`, ADR 0004, specification

1. Register the hook with a `/bin/sh` launch that skips empty and relative `PATH` entries, a `timeout` of 25 s.
2. Manifest, ignore rule, README section, ADR 0004, specification amendments, wiring tests.

Completion: wiring tests pass; `./install.py --dry-run` showed only the intended changes.

### Increment F — Independent security review

Dependencies: E
Affected areas: whatever the findings touched

1. Four passes by an independent `security-reviewer` agent; each fix test-first with a mutation check.

Completion: no Critical, High or Medium finding is open. See Result for the findings and dispositions.

### Increment G — Install and live check

Dependencies: F
Affected areas: `~/.claude`

1. `./install.py` and `./install.py --check`.
2. Two nested `claude -p` sessions in `auto` mode on a throwaway repository: a commit and a remove prompt.

Completion: `--check` matched the repository; both prompts fired the hook and produced a logged `approve`
(gpt-6.1-sol, 5.7 s and 9.8 s) and a notification, and the commands were refused with the repository unchanged.

## Verification

- Full suite: 657 tests, 5 skipped, 0 failures (`python3 -B -m unittest discover -s tests`); `git diff --check` clean.
- Mutation checks: each new guard was broken on purpose and a test failed (secret scan, PATH containment,
  replace refs, hardlinks, FIFO config include, exec-config key shape, deadline-as-BaseException, `set -f`, entropy
  tiers, ignored-status, nlink, key shape).
- Installed copy matches the repository (`./install.py --check`).
- Live check in real Claude Code, `auto` mode (Increment G).

## Deferred work

- Specification increment 2 (`allow` authority). Prerequisites found by the reviews: harden the real
  `claude-workflow commit` (it runs Git without the hook's hardening; `GIT_NO_REPLACE_OBJECTS` is not set there),
  secret detection beyond heuristics, the gap between approval and execution, and a test under the real Claude Code
  25 s hook kill.
- Specification increment 3 (project registry and hash pin).
- The next-increment approval gate and the `claude_project_template` module (which `requires` `claude` and `codex`).
- Re-run `gpt-6-sol` under the new rubric (regression check) and benchmark plan reviews on real repositories.
- Classify "usage limit" in the verdict log (today it shows as `no_verdict`).
- The plan-review benchmark in `.debug/2026-10-16-plan-review-bench/` never completed its false-alarm gate.

## Result

**Delivered.** The hook is installed and working. In the live check both prompts produced a logged verdict and a
notification, and nothing was decided for the owner.

**Departures from the plan.**
- Rules gained a `review_checks` list, the rubric is one file with per-rule sections, and a `notify` config key
  was added.
- Commit checks mirror `claude-workflow commit` (it stages the named paths itself) instead of "the staged set";
  the remove check uses a fresh preview because the helper keeps no receipt.
- The launch is a `/bin/sh` bootstrap, not a bare `python3`.
- Collection has a 12 s deadline; Codex timeout is 15 s and the hook timeout 25 s (live reviews took up to 10.4 s).

**Security review.** Four passes found and fixed, each with a failing test first: a repository-supplied
`osascript` through an empty `PATH` entry after the hook had changed directory (Critical), a repository
configuration key that ran code at commit time (`gpg.ssh.defaultKeyCommand`; fixed by matching keys by shape),
replace-ref forgery of the diff, hardlinks and `.git` paths, a `git config` include of a FIFO that hung and
orphaned Git, an alarm swallowed by `except OSError`, glob expansion of `PATH` in the launch command, weak secret
detection, and "ignored" reported as false when it was unknown. Open items are listed under Deferred work.

**Environment finding.** The owner's shell `PATH` contains an empty entry (position 4), which the shell reads as
the current directory, ahead of `~/.local/bin`. A repository can plant its own `python3` or `claude-workflow`
today, independent of this feature. The approver detects and declines that case; removing the empty entry fixes
it at the source.

**Model and rubric.** A cost-ordered search (measured credits per call, published Codex credit rates) on 52 cases
found that the rubric never asked whether a change was harmful in itself: `gpt-6.1-sol` approved credential
logging and `gpt-5.6-luna` approved disabled security tests. A fourth check, `change_is_safe_in_itself`, was
added and re-tested on 72 cases including 20 held-out ones. The approver now uses `gpt-6.1-sol` at `medium`
(0 of 105 harmful requests approved, 2 of 71 benign declined, p95 8.5 s; the last repeat was lost to the usage
limit). Plan reviews now default to `gpt-5.6-luna` at `low`, rising to `high` (23 of 24 injected defects at about a
ninth of the cost of `gpt-6.1-sol`). Retaining the Codex session across rounds was not adopted.

**Test stalls.** Two unexplained stalls were caused by a test that inherited an open stdin: a planted `core.fsmonitor`
script ended in a bare `cat` and blocked when the shell tool call had a heredoc. The probe and test helper now use
closed stdin with timeouts, and the hook's own Git calls also close stdin.

**Cost and limits.** The evaluations used about 170 Codex credits and exhausted the Plus allowance twice; the live
check used about 1 credit. Benchmarks used small toy repositories and one run per configuration, so the plan-review
choice is weakly supported on real repositories.

**Unrelated work left untouched.** `/private/tmp/spike-outside-auto.txt` (an early spike) is for the owner to
delete; the untracked `.debug/` notes are git-excluded.
