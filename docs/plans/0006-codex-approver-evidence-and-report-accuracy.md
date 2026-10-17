# 0006: Codex approver evidence and report accuracy

Status: Completed
Created: 2026-10-16
Completed: 2026-10-17

## Outcome

Make the Codex approver's advice-only log trustworthy and wide enough to judge
whether it could later decide in the owner's place: remove the false
`no_secret_lines` declines seen on real commits, and log verdicts plus
owner outcomes for `git push` and `remote-runner submit|fetch|cancel|prune`,
so `--report` shows Codex/owner agreement for them.

## Scope

- Tighten the high-entropy token heuristic and record which token class
  tripped it (no token text).
- Extend the engine from one tool (`claude-workflow`) to `git push` and
  `remote-runner`, with a fact collector, deterministic checks and rubric
  section per new rule, still advice-only.
- Add `PostToolUse` / `PostToolUseFailure` outcome hooks for the new spellings.
- Update `docs/specs/codex-approver.md` and ADR 0004; mirror to `~/.claude`.
- Increment F: record the shape (never the arguments) of prompts that match no
  rule, with a `--report --unmatched` view.
- Increment H: pair verdicts with outcomes that arrive before the verdict row,
  so `--report` agreement is not understated.
- Increment I: let the `remote-runner submit --best` host check pass from local
  facts.

## Non-goals

- Any `allow` authority (increment 2 of the spec) or change to `ask`/`deny`
  rules or `defaultMode`.
- Changing how `claude-workflow commit`/`remove` are decided.
- Project-level rules, registries, or `claude_project_template` changes.
- Pushing, submitting, fetching or pruning anything as part of verification
  beyond fixtures and tests.

## Assumptions and constraints

- **Decision needed from the owner:** the spec lists `git push` as a
  permanent non-goal ("stay with the owner permanently"). This plan logs
  advice only, which does not approve anything, but the owner now wants push
  evidence "for consideration of approving". Increment C amends that
  non-goal to "advice-only logging; any authority needs a separate ADR".
  Approving this plan approves that amendment.
- The engine is not purely data today: `SUPPORTED_TOOLS`, `SPELLINGS`, the
  tokenizer entry (`split_command`) and `positionals == "paths"` are specific
  to `claude-workflow`. Generalising them is the main design work and a
  security-sensitive change (command parsing, subprocess facts).
- Advice-only means a hook failure never blocks a prompt (spec "Failure
  behavior"); preserve that.
- The hook sees only `ask`-rule prompts; `git push` and the four
  `remote-runner` subcommands are already on the ask list.
- Logs hold no command output, no token text, no secrets.

## Discovery and impact evidence

Graphify: skipped — no graph exists in this repository and the affected files
are fully enumerated: `hooks/codex_approver.py`, `codex-approver/rules/`,
`codex-approver/rubric.md`, `settings.json`, `settings-policy.txt`,
`config-manifest.txt`, `docs/specs/codex-approver.md`,
`docs/decisions/0004-*.md`, `tests/test_codex_approver_*.py`,
`tests/test_permissions.py`, `tests/test_install.py`.

Verified against current source and logs (2026-10-16): both post-fix real
declines (`verdicts.jsonl` 18:15 and 18:19 UTC) were `no_secret_lines` with
no Codex call. Running `has_secret` on the diffs showed no secret pattern
matched; the hits were `token_is_suspect` on a 64-hex SHA-256 on a line
without a checksum word, a remote-runner job ID, and `$HOME/datasets/...`
paths (`TOKEN_RE` includes `/`, `_`, `-`).

## Completion criteria

- The two real diffs (`da1094f`, `4edc286` in the othello repo, captured as
  fixtures) no longer fail `no_secret_lines`; fixtures with a real-looking
  key, JWT and AWS key still do.
- A prompt for each new command shape yields a logged verdict (or a logged
  deterministic decline) and, after you run it, an outcome row; `--report`
  lists them per rule.
- Full test suite passes; security review of the parsing/collector changes
  has no unresolved finding; `git diff --check` clean; `~/.claude` mirror
  matches the repository.

## Increments

### Increment A — Fix false-positive secret declines

Dependencies: None
Affected areas: `hooks/codex_approver.py`, `tests/test_codex_approver_engine.py`, `tests/fixtures/`

1. Capture the two diffs (minimised, no real data beyond the digest and
   paths) as fixtures; add failing tests first.
2. Change `TOKEN_RE`/`token_is_suspect`: split path-like tokens on `/`; exempt
   a bare hex digest when the previous line or the same line mentions a
   checksum context; exempt `\w+--\w+--\d{8}-\d{6}--[0-9a-f]{8}` job IDs.
   Keep every `SECRET_PATTERNS` rule untouched.
3. Add `secret_kinds` (e.g. `long_hex`, `high_entropy`, `pattern:<n>`) and
   the path (not the token) to the logged `secret_hits`.
4. Run the engine test suite.

Completion: new tests pass, existing secret tests unchanged and passing.

Outcome: done in `a4b04b8` (pushed); hook synced to `~/.claude`; full suite 684 OK.

### Increment B — Generalise the engine to more tools

Dependencies: A
Affected areas: `hooks/codex_approver.py`, rule schema, `tests/test_codex_approver_rules.py`

1. Inspect `remote-runner` and `git push` grammars; write down the exact
   argument shapes to accept (everything else: no decision).
2. Make spellings and supported tools rule-driven; allow positionals other
   than `paths` (e.g. `remote`, `refspec`, `job`, `profile`); keep the
   tokenizer's refusal of operators, substitution and globs.
3. Tests: unknown shapes, compound commands and look-alike spellings yield no
   decision; `claude-workflow` behavior unchanged.

Completion: existing rule tests unchanged; new parse tests pass.

Outcome: done in `14792b9` (not pushed; hook not yet synced to `~/.claude`); full suite 703 OK, 5 skipped.
Rule files for the new tools do not exist yet, so live behavior is unchanged. `load_helper` remains
claude-workflow-only; C's collectors must not reuse it for `remote-runner` or `git`.

### Increment C — Rules, collectors, checks, rubric, hooks

Dependencies: B
Affected areas: `codex-approver/rules/*.json`, `codex-approver/rubric.md`, `hooks/codex_approver.py`, `settings.json`, `settings-policy.txt`, `config-manifest.txt`, spec, ADR 0004

1. `git push`: collector reports branch, remote and URL host, refspec,
   force/tags/delete flags, target ref is default branch, commits ahead
   (subjects, paths), and a secret scan of the outgoing diff. Checks: no force
   or delete, not a tag, secret scan clean, upstream known.
2. `remote-runner submit` (incl. `--snapshot`): profile, remote, resolved
   commit, reachable from remote, clean tree; `fetch`: target path, `--force`,
   artifact hash policy; `cancel`: job exists and is owned/running; `prune`:
   preview only, `--apply` flagged. Read-only collectors using only declared
   `remote-runner` commands.
3. Add rubric sections, outcome hooks for the new spellings, spec and ADR
   text, and the non-goal amendment.
4. Tests per rule with hostile fixtures (reviewer-directed text in commit
   subjects, branch names, profile names).

Completion: each rule produces a verdict and outcome in a temp-log test run;
`--report` shows them.

Owner decision (2026-10-16): collectors use local facts only. No SSH, no
`git ls-remote`, no `remote-runner status` from the hook; remote-side facts are
absent from FACTS and the rubric says so.

Slice 1, `git push` (rule `git-push`): collector, eleven checks, `push` rubric
section, `Bash(git push:*)` outcome hooks, manifest entry and per-rule
`--report` table are done; 29 push tests added. Slice 2 (`remote-runner
submit|fetch|cancel|prune`), the spec and ADR 0004 text and the non-goal
amendment remain.

Slice 2 done in the working tree: four `remote-runner-*` rules with
collectors, checks, rubric sections, 20 outcome-hook patterns per event,
manifest entries, spec and ADR text (non-goal amended), and 27 runner tests.
Not yet done: security review (D) and `~/.claude` sync (D); sync the hook
before the rule files.

### Increment D — Review and mirror

Dependencies: C
Affected areas: whole change set

1. `security-review` with adversarial verification of parsing and collectors.
2. Sync `~/.claude`; confirm mirror equality; run the full suite.
3. Live check: owner triggers one prompt per new shape (push to a throwaway
   branch is **not** done by Claude); inspect the log.

Completion: review clean; owner-observed log rows for each shape.

Review (2026-10-16, `security-reviewer` agent plus one bypass round): no Critical
or High finding; hostile repository configuration executed nothing during
collection (tested with recording stubs). Fixed with regression tests: merge
commits hid paths and secrets from the push scan (`-m`); forged remote-tracking
refs hid outgoing commits (new `tracking_refs` fact and an `outgoing_trusted`
check that also declines an empty outgoing set); `--dest '~'` was judged
differently from the real tool; a fetch destination outside the repository now
declines; a checksum word no longer exempts a whole line (only hex digests and
exact-length `shaN-` integrity values); names and paths in push facts are
scanned for secret patterns. Accepted residual risk: slash-containing and
40-hex secrets can evade the entropy heuristic (patterns remain the floor); a
repository can claim any project id for the cancel check; the tracking-ref
reflog is forgeable, so that fact is advisory; `git config`/`remote` reads are
bounded only by the 12 s deadline. Not run: huge-history and FIFO cases,
hostile global config, malformed rule JSON, settings `if` diff against `ask`.
Still to do: sync to `~/.claude` (hook file first, then rules, rubric,
settings, manifest) and the owner's live check.

### Increment E — Advice for `ask-codex archive` (approved by the owner 2026-10-16)

Dependencies: C, D (engine, wiring, sync flow)
Affected areas: `hooks/codex_approver.py`, `codex-approver/rules/ask-codex-archive.json`, `codex-approver/rubric.md`, `settings.json`, `config-manifest.txt`, spec, ADR 0004, `tests/test_codex_approver_*.py`

`ask-codex archive` is already on the `ask` list (five spellings). It closes a
plan review: it marks the state closed, renders the ledger and prints the
summary; it makes no Codex call and changes only review state under `.debug/`.
Closing is the point after which no more rounds run without an owner `reset`,
so it is worth measuring whether Codex and the owner agree on when a review is
finished. Advice-only, local facts, no `allow` authority, as in C.

1. Read `bin/ask-codex` (`open_review`, `read_state`, `state_directories`, plan
   key rules) and write down the exact state fields and file shapes to read;
   do not import `ask-codex` into the hook.
2. Engine: add tool `ask-codex` with its five spellings and installed path;
   grammar `ask-codex archive [--plan <file>]`, no positionals.
3. Collector `archive` (read-only; all output is untrusted). Step 1 found that
   `ask-codex status --plan=<plan>` is a local, read-only command that verifies
   the review state's HMAC seal itself and reports rounds used, bound,
   `closed`, `blocked`, grants and `pending_decisions` (undecided blocker or
   major findings). The collector runs that installed command under the
   approver's hardened Git environment with a short timeout and an output cap,
   and keeps only those fields. The hook never reads the seal key or the round
   files. Rejection reasons and last-round convergence are not in `status`
   output, so they are not facts.
4. Deterministic checks: the installed `ask-codex` resolves as the shell would;
   `status` succeeded (which also means the plan path is a regular file inside
   the repository and a verified review state exists); no secret-looking text.
   Undecided findings, a block, or zero rounds are facts for Codex, not
   declines.
5. Rubric section `ask-codex-archive` with semantic checks
   `review_is_finished` and `no_reviewer_directed_text`.
6. Outcome hooks (`PostToolUse`/`PostToolUseFailure`, five patterns), manifest,
   wiring test, spec and ADR sentence; tests with a scratch review state and
   hostile text in plan path, finding text and rejection reasons.
7. Security-review the new parser/collector, sync to `~/.claude`, and have the
   owner trigger one real `ask-codex archive` prompt.

Completion: a verdict and an outcome row for `ask-codex archive` in a temp-log
run and one owner-observed row; `--report` lists the rule; suite passes.

Outcome (2026-10-16): steps 1-6 done in the working tree; 15 archive tests
added. Security review (`security-reviewer`): no Critical or High finding.
Low, fixed with a regression test: a FIFO planted as the review's
`state.json` made `ask-codex status` hang and a blocking read ignored the
timeout; the status read now runs under a timer in its own process group and
is killed as a group. Verified by test: the status path writes nothing and
makes no network or Codex call; hostile repository Git config ran nothing;
hostile status output (huge, deeply nested, non-UTF-8, wrong types) fails
closed; `--plan=<value>` cannot become an option; an edited or foreign state
shows as tampered or not found. Accepted residual risk: whoever can write
`.debug/` can choose which valid sealed snapshot is current (the real
`archive` behaves the same). Not run: the real harness hook kill, and
case-insensitive filesystem aliasing. Still to do: commit, sync to `~/.claude`
(hook file first), and one owner-observed `ask-codex archive` prompt.

### Increment F — Log prompts that match no rule (approved by the owner 2026-10-17)

Dependencies: C (engine, wiring)
Affected areas: `hooks/codex_approver.py`, `docs/specs/codex-approver.md`, ADR 0004, `tests/test_codex_approver_*.py`

Today a `PermissionRequest` that matches no rule exits without a trace, so the
owner cannot see which commands keep prompting. The hook already receives every
Bash prompt (unfiltered matcher), so it can record the unmatched ones. This
adds no authority and no Codex call; it is a frequency list for deciding which
`allow` entries or approver rules would remove the most prompts. It sees only
commands that prompt: allow-listed commands never reach the hook.

1. In `process()`, when `match_event` finds no rule, append one row to
   `log/unmatched.jsonl` (separate from `verdicts.jsonl`, so agreement numbers
   stay clean) and exit 0 as before. A logging failure never blocks a prompt.
2. Row fields: timestamp, safe session id, `shape`, `compound` flag, command
   SHA-256. `shape` is the leading command plus up to two non-option words
   (for example `git ls-tree`, `uv run`), taken after env-assignment prefixes;
   a token that looks secret-like (`secret_kind`) truncates the shape to the
   first word. No arguments, paths or full command text are stored.
3. A command with `;`, `&&`, `||`, a pipe, `$(`, a backtick or a newline
   outside quotes is logged with `compound: true` and a `segments` list with
   the shape of each command in it (skipping `cd`, assignments and shell
   keywords), since compound commands are a common cause of unexpected prompts
   and `cd x; remote-runner cancel $J | tail` would otherwise show only `cd`.
   The primary `shape` is the first real command. A heredoc body is cut off.
4. `--report --unmatched [--days N]` lists shapes ranked by count with first
   and last seen and the compound share. The same size cap and rotation as the
   other logs apply (`max_log_bytes`).
5. No outcome row for unmatched commands (that would need broader `Post*`
   patterns); revisit only if the frequency list proves too thin.
6. Tests: a rule-matching command writes no unmatched row; an unmatched one
   writes exactly one with the expected shape; compound, env-prefix, secret-like
   and non-UTF-8 inputs; log write failure still exits 0 with no stdout; the
   row never contains arguments; report ranking and `--days`.
7. Spec and ADR 0004 sentence (advice-only, shape-only, no arguments logged);
   security-review the shape extraction (it handles untrusted command text);
   sync to `~/.claude` (hook file first).

Completion: unmatched prompts in a temp-log run appear as shape rows and in
`--report --unmatched`; matched prompts are unchanged; suite passes; mirror
matches.

Outcome (2026-10-17): steps 1-7 done in the working tree except commit and sync;
25 tests in `test_codex_approver_unmatched.py`, 283 approver tests pass.
Security review (`security-reviewer`): no Critical or High finding. Fixed with
regression tests: (Medium) words inside a quoted or escaped env-assignment value
became the program, and text after a `$(...)` or backtick substitution became
a new command; quoted, escaped and substituted text is now masked before
splitting, and a substitution's commands are listed after the outer ones;
(Low) free-text subcommands (`ask-codex hunter2`, `make <target>`) were kept, so
a subcommand is kept only from a fixed per-tool list; (Low) report text could
carry terminal escapes, one malformed row (`segments` not a list), a deeply
nested JSON line, or a huge `--days` aborted the report; these are now
sanitised, skipped, caught and bounded. A 60,000-case fuzz of random quote,
operator and substitution combinations found no argument text in a row.
Accepted residual risk: a program name is kept as typed when it looks like a
plain word, so a short secret typed as the command word itself (under 12
characters, or without digits) is stored; words of 12+ characters with a digit,
secret patterns and high-entropy words become `<other>`. Quote-aware masking
treats heredoc bodies and `<<` conservatively (cut at the first newline).
Still to do: commit, sync to `~/.claude` (hook file only), and watch real
`--report --unmatched` output.

### Increment G — Fewer false secret declines in lockfiles and tests (approved by the owner 2026-10-17)

Dependencies: A (secret scan), F (`secret_paths` made the cause visible)
Affected areas: `hooks/codex_approver.py` (`secret_kind`, the commit collector),
spec, `tests/test_codex_approver_*.py`

Real declines from the cribbage repo: `web/package-lock.json` (66 lines of
package names and URLs flagged `high_entropy`) and `tests/web/test_protocol.py`
and `test_websocket.py` (`token="abc_DEF-123"` style fixtures hit the generic
assignment pattern). Both are advisory declines on harmless commits.

1. Lockfiles: for a file whose basename is a known lockfile (`package-lock.json`,
   `npm-shrinkwrap.json`, `yarn.lock`, `pnpm-lock.yaml`, `Cargo.lock`, `go.sum`,
   `poetry.lock`, `uv.lock`, `Pipfile.lock`, `composer.lock`, `Gemfile.lock`,
   `flake.lock`) skip the entropy heuristic only. Every secret pattern still runs.
2. Tests: for a file with a `tests`, `test` or `__tests__` directory component
   skip only the two generic `password|secret|token|api_key = "value"` patterns.
   The specific patterns (AWS key, GitHub/Slack/GitLab/npm tokens, JWT, private
   key, bearer, `aws_secret_access_key`/`client_secret`/`private_key`
   assignments, URL credentials) and the entropy heuristic still run.
3. Applies to the file diffs of `claude-workflow commit` only; the commit message
   and the push diff keep the full scan.
4. Tests: lockfile package names no longer decline while a real token pattern
   inside a lockfile still does; a fixture `token="..."` under `tests/` no longer
   declines while a GitHub-shaped token there does; the same line outside
   `tests/` and a `tests`-named file (not directory) still decline.
5. Spec sentence; sync the hook file to `~/.claude`.

Accepted risk: a file placed under a `tests/` directory can carry a generic
`password = "..."` assignment without a `pattern` decline, and a lockfile can
carry an unflagged random token that no pattern recognises. The approver is
advice-only and Codex still reviews the diff.

Completion: the two real cribbage commits' file contents no longer fail
`no_secret_lines`; suite passes; mirror matches.

Outcome (2026-10-17): steps 1-4 done in the working tree; 7 tests in
`test_codex_approver_pathscan.py`, 290 approver tests pass. The real
`web/package-lock.json`, `tests/web/test_protocol.py` and `test_websocket.py`
from the cribbage repo scan clean with the path options and flagged without
them. Not run: an independent bypass review (the change only relaxes two
checks for path-selected files); the path match is case-sensitive, so
`Tests/` or `Cargo.LOCK` keep the full scan. Still to do: spec sentence is
written; commit and sync.

### Increment H — Pair verdicts with outcomes that arrive first (requested by the owner 2026-10-17)

Dependencies: C (outcome hooks), the `--report` pairing in `build_report`
Affected areas: `hooks/codex_approver.py` (`build_report`, verdict timestamp),
spec, `tests/test_codex_approver_*.py`

Evidence (2026-10-17, read-only): the verdict row is appended after Codex
answers (5-10 s), but the approver is advice-only, so the owner can answer the
prompt first. In 15 of 40 real rows the outcome is stamped 1-5 s before the
verdict. `build_report` requires `0 <= outcome_ts - verdict_ts <= window`, so
those pairs were counted twice: as "approved, not run" and as "ran without a
prompt". By session and command hash every verdict with outcome data was
followed by the command running (all approves, and all 8 declines, a result the
report hid for one decline).

1. Stamp each verdict row with the time the hook started, in addition to the
   append time (`ts` stays the append time so older rows keep their meaning).
2. Pair on session and command hash within `-window_early <= delta <= window`,
   where the early bound is small and named (60 s), and prefer the nearest
   unused outcome when a command repeats. Rows without the new field use the
   early bound against `ts`.
3. "Awaiting an answer" counts only verdicts with no outcome and younger than
   the window.
4. Tests: outcome 3 s before the verdict pairs; outcome 90 s before does not;
   a repeated command pairs each verdict with its own outcome; a decline whose
   outcome precedes it reports as an override; old rows without the new field
   still pair.
5. Spec sentence; sync the hook file to `~/.claude`.

Completion: re-running `--report` on the current logs shows no "ran without a
prompt" for pairs that share a session and hash, and the approve/decline
totals match the hash-join figures above; suite passes; mirror matches.

Outcome (2026-10-17): steps 1-5 done in the working tree except commit and sync.
`PAIR_EARLY = 60` s; pairing takes the nearest unused outcome by `started_ts`
(or `ts` on older rows); 5 new report tests, one existing test changed from a
50 s to a 90 s early outcome, and a `started_ts <= ts` assertion; 295 approver
tests pass. The repo hook run on the live logs reports 45 verdicts, 0 awaiting,
0 "ran without a prompt", and every verdict that has outcome data followed by
the command running (32 approve, 9 decline, 1 decline that failed). Remaining
"not run" rows (2 approve, 1 decline) are the three 2026-10-16 17:14-17:25 rows
logged before outcome rows existed; they have no outcome data, so the 73%
agreement figure still mixes them in. Excluding rows older than the first
outcome row is not done. Still to do: commit and sync (hook file first).

### Increment I — Host check for `remote-runner submit --best` (requested by the owner 2026-10-17)

Dependencies: C (remote-runner collector and rubric)
Affected areas: `hooks/codex_approver.py` (submit facts), `codex-approver/rubric.md`,
`codex-approver/rules/remote-runner-submit.json`, spec, tests

Evidence (2026-10-17, cribbage): a bare `remote-runner submit --best --profile
search-bench --snapshot` was declined on `host_selection_is_appropriate`
because the facts show no remote capabilities, so Codex "cannot establish"
that the host meets the profile's Linux and eight-core requirements. The owner
ran it and it succeeded. The criterion cannot pass for `--best`, where
`remote-runner` chooses the runner itself from declared requirements.

1. Facts stay local: no SSH and no `remote-runner recommend`. Add to the submit
   facts what the local remote configuration and the profile already declare:
   configured remote names, the profile's declared requirements, and for a named
   remote its declared labels when the local config holds them (confirm in the
   code what the config exposes before writing the check).
2. Rubric: for `--best`, the criterion passes when the profile declares
   requirements and at least one remote is configured, because `remote-runner`
   itself refuses an ineligible or unavailable runner. For a named remote it
   passes only when that remote is configured and, where its labels are known,
   they satisfy the profile. Anything else, including an unknown remote or a
   `--best` with no declared requirements and no configured remote, still fails.
3. Tests: `--best` with requirements and a configured remote passes; `--best`
   with no remotes fails; a named unknown remote fails; a named remote whose
   labels miss a requirement fails; the real cribbage `search-bench` shape as a
   fixture.
4. Spec and rubric text; sync hook file first, then rules and rubric.

Completion: the cribbage `search-bench` submit fixture no longer declines on
`host_selection_is_appropriate`; fixtures that should decline still do; suite
passes; mirror matches.

Outcome (2026-10-17): steps 1-3 done in the working tree; commit and sync
pending. The owner's remotes file declares per-remote `capabilities` (`os`, `arch`,
`cpu_cores`, `memory_gib`, `labels`), so the collector now computes
`host_eligibility` (configured, eligible, ineligible with reasons, and
`named_remote_eligible`) with a local copy of `remote-runner`'s
`capability_mismatches`, failing closed when a profile requirement was dropped
(`requirements_ok`). The rubric criterion reads those facts instead of guessing.
It is a rubric change only; no deterministic check or rule JSON changed. 9 new
tests in `HostEligibilityTests`, including a parity test against the real
`bin/remote-runner`; 304 approver tests pass. On the real cribbage contract the
collector reports `ned` eligible for `reproduce` (linux, 8 cores) and
`web-check`. Not run: the `search-bench` profile no longer exists in the working
tree, so the exact failing command was not replayed; Codex itself was not
re-run on it (the live rubric is not synced); no independent security review
(the change adds facts from a file the collector already read, and no host
detail enters them). Still to do: commit; sync hook file, then rubric; watch the
next real `submit --best` prompt.

## Verification

- Repository test suite: `python3 -B -m unittest discover -s tests` passed on 2026-10-17 after the last
  increment (828 tests, OK, 5 skipped); the approver modules alone run 304 tests.
- `python3 ~/.claude/hooks/codex_approver.py --report` and `--report --unmatched` on the live logs.
- `git diff --check` clean; `python3 -B install.py --check --no-link-bin` reports the mirror matches.

## Risks and sensitive actions

- Parsing and subprocess facts for push/remote-runner are
  security-sensitive; collectors must never execute request-supplied text and
  never contact the network except via already-declared commands.
- Loosening the entropy heuristic could let a real secret reach Codex's facts;
  patterns stay as the hard floor and tests cover real-shaped secrets.
- Logs may contain branch names, subjects and paths; they stay local and
  unmirrored.
- No push, commit or settings permission change happens without separate
  explicit approval.

## Deferred work

- Allow authority (spec increment 2) and an ADR for any approval of push or
  remote-runner, decided only after a longer evidence period.
- A `token_kind` summary in `--report`.
- Live evidence for `remote-runner prune --remote ned` (never prompted during the
  evidence period) and a post-fix `submit --best` verdict (Increment I).
- Exclude verdicts logged before outcome rows existed from the agreement figure
  (the live logs were pruned of them instead).
- Independent bypass reviews for Increments G and I (not run; both only add or
  relax facts for path- or file-selected input).
- Case-insensitive path matching for the lockfile and `tests/` options.
- A `--repo` option for `claude-workflow commit`, so a commit in another repository
  needs no `cd` prefix.
- Compound commands (`cd x && remote-runner ...`, pipes, `2>&1`) still go unlogged
  by design; the global CLAUDE.md asks for bare commands instead.

## Result

Increments A-I are done, committed and pushed (`faa303b` through `9c0a454`),
the hook file and rubric are synced to `~/.claude`, and no `allow` authority was
granted; the approver stays advice-only.

- **A-B:** the false `no_secret_lines` declines are fixed (the entropy heuristic is tighter and
  records the token class, not the text) and the engine handles more than one tool.
- **C-E:** rules, collectors, deterministic checks, rubric sections and outcome hooks exist for
  `git push`, `remote-runner submit|fetch|cancel|prune` and `ask-codex archive`.
- **F:** prompts that match no rule are logged by shape only, with `--report --unmatched`.
- **G:** lockfiles and `tests/` fixtures no longer decline on harmless content.
- **H:** `--report` pairs a verdict with an outcome that arrives up to 60 s before it; the old
  pairing counted such pairs twice and understated agreement (45% on the raw logs).
- **I:** `host_eligibility` lets the `submit --best` host check pass from local facts, using a copy
  of `remote-runner`'s own capability matching (a test keeps the two in step).

Live evidence on 2026-10-17 (bare commands in the cribbage and othello projects): `git push`
(2 approved, ran), `ask-codex archive` (2 approved, ran), `claude-workflow commit` and `remove`
(many), and `remote-runner submit` (a verdict and outcome per prompt; both prompts declined on the
host check that Increment I then fixed, and were removed from the logs with the other rows caused by
fixed bugs and the live-test rows). After that cleanup the live report shows 36 verdicts: every one of
the 32 approvals was followed by the command running, and 4 declines were overridden by the
owner (a `no_secret_lines` cause logged before it was recorded, a stale expected head, and a Codex
scope judgement); agreement is 89%. The pre-cleanup originals were not retained.

Fixture-tested only, by the owner's decision on 2026-10-17: `remote-runner fetch` and
`remote-runner cancel`. `remote-runner prune` also has no live evidence because no prompt occurred.

The first live `submit --best` after Increment I, and any live `prune`, should be checked with
`--report`. Compound commands were the main cause of unlogged prompts and are handled by the
CLAUDE.md guidance, not by the approver.
