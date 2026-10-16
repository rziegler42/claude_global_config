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

### Increment D — Review and mirror

Dependencies: C
Affected areas: whole change set

1. `security-review` with adversarial verification of parsing and collectors.
2. Sync `~/.claude`; confirm mirror equality; run the full suite.
3. Live check: owner triggers one prompt per new shape (push to a throwaway
   branch is **not** done by Claude); inspect the log.

Completion: review clean; owner-observed log rows for each shape.

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
