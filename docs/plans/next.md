# Next plan

Status: In Progress
Created: 2026-10-16

## Goal

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

## Verification

- Repository test suite (`python3 -m unittest` / the commands the repo
  documents; confirm in step A.4).
- `python3 hooks/codex_approver.py --report` after live prompts.
- `git diff --check`, mirror diff against `~/.claude`.

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
  remote-runner, decided only after the evidence period.
- A `token_kind` summary in `--report`.

## Result

<!-- Complete this only after verification. Archive the plan according to
README.md, then reset this file to the empty template. -->
