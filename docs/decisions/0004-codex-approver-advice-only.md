# 0004: A Codex approver for trusted helper prompts, advice-only first

Status: Accepted
Date: 2026-10-16
Amended by ADR 0005: `claude-workflow commit` alone may now be allowed; everything else here stands.

## Context

The owner is prompted for `claude-workflow commit` and `claude-workflow remove`
even though those helpers enforce their own protections, and they trust Codex to
judge such a request in their place. Experiments on Claude Code 2.1.301 showed
that a `PermissionRequest` hook fires for prompts raised by `ask` rules in every
permission mode including `auto`, that a hook `allow` satisfies such a rule, and
that a settings `deny` rule still wins and the hook never runs. A hook that
makes no decision leaves the normal prompt, and a hook that fails or exceeds its
timeout is discarded. The request, the commit message, file names and file
contents are all untrusted: a hostile repository or a misled assistant controls
them.

## Decision

Add `hooks/codex_approver.py`, a `PermissionRequest` command hook, with the data
in `codex-approver/`.

- **Rules are data.** One JSON file per approvable command names the exact
  command grammar, the collector, the deterministic checks, and the semantic
  checks Codex judges. A command with no rule is never decided. Adding a command
  with existing collectors and checks is a rule file plus a fixture.
- **Gate first, Codex second.** The raw command must begin with one of the five
  literal spellings the `ask` rules use, and the remainder must tokenize as
  plain literals. Trusted code then collects the facts; fixed checks run on
  them; only a request that passes every check is sent to Codex, which can
  confirm or veto and can never promote a command the gate rejected.
- **Trusted facts.** The collector imports the installed `claude-workflow` and
  reuses its validators, so the gate cannot drift from the helper. Git runs with
  the environment scrubbed and repository configuration overridden, and no
  working-tree diff is run through Git (clean filters would execute repository
  code); changes are computed in Python from raw blobs and file bytes.
- **Invocation is verified.** The command is resolved as the shell would resolve
  it. A relative or empty `PATH` entry that holds the tool, an entry inside the
  repository, or a helper or interpreter that is not the installed one declines.
- **Codex is isolated.** It runs read-only from an empty temporary directory
  with a minimal environment and receives only a rubric and one line of
  JSON-escaped facts between nonce-delimited markers. Its reply must match a
  strict schema; anything else is no verdict.
- **Advice-only.** The hook never prints a decision. Its verdict goes to a local
  log and a notification, and the normal prompt appears as before. Config
  `mode` accepts only `advise`. Granting `allow` is a separate decision.
- **Failure is the normal prompt.** Any error, timeout or unexpected input
  yields no output and exit 0.

## Alternatives considered

- **Command-only judgement.** Codex cannot judge a commit from a command line.
  Rejected; the gate collects the facts instead.
- **Codex judges everything.** Slower, costlier, and puts the whole safety
  decision in a model that reads attacker-influenced text. Rejected.
- **A `PreToolUse` hook.** Fires on every call in every mode and costs a check
  per call, while `PermissionRequest` sees exactly the prompted actions.
  Rejected.
- **Advice for more commands, still no authority.** `git push`,
  `remote-runner submit|fetch|cancel|prune` and `ask-codex archive` have advice-only rules, so the log
  and `--report` can show whether Codex and the owner agree before anyone
  considers delegating them. Their collectors use local facts only (no SSH or
  network), and the spec's earlier "push stays with the owner permanently" is
  amended to "advice-only logging; any authority needs a separate ADR".
- **A shape-only log of prompts no rule covers.** The hook already receives
  every Bash prompt, so it records the shape (never arguments) of the ones
  without a rule in `unmatched.jsonl`. The owner can then see which commands
  keep prompting and which `allow` entries or rules would remove the most
  prompts. It decides nothing.
- **Project-level rules that widen trust.** A repository's own file is
  attacker-controlled. Deferred to a user-side registry that pins a file hash.

## Consequences

- Prompts cost one Codex call of about 5 to 10 seconds before the dialog appears.
  A slow or absent Codex only removes the advice.
- Binary or oversized changes, credential-looking names, and secret-looking
  content decline and go to the owner as today.
- Request text and diff content reach OpenAI only after every deterministic
  check passed, and never contain a detected secret.
- The hook is launched by a `/bin/sh` bootstrap that runs the first absolute
  `PATH` entry's `python3`, skipping empty and relative entries.
- The owner's live `PATH` contains an empty entry, which already lets a
  repository shadow `python3` or `claude-workflow` when run from its root. The
  approver detects and declines that case; it does not fix the shell setup.
- The real `claude-workflow commit` runs Git without the hook's hardening, so a
  repository that configures filter drivers, hooks, a signing program or a diff
  program could make an approved commit run them. A deterministic
  `repo_config_safe` check declines any such repository (names only, never
  values). The helper itself is not hardened; that, a heuristic secret scan,
  and the gap between approval and execution remain for any `allow` authority.
- Outcome hooks (`PostToolUse`, `PostToolUseFailure`) record whether a covered command ran, without its output, so
  `--report` can compare each verdict with what the owner did. They add no decision power.
- Fact collection has a 12 s deadline and bounded Git calls, so a hostile
  repository costs the advice, not a hang.
- For push and remote-runner the facts are partial by design: the remote is
  never contacted, so "ahead of remote" means ahead of the last fetch and job
  state is unknown. Agreement measured on these rules says less than for
  commit and remove.
- Behavior was observed on macOS and Claude Code 2.1.301 only.

## Verification

`tests/test_codex_approver_engine.py`, `tests/test_codex_approver_rules.py`,
`tests/test_codex_approver_codex.py` (a fake Codex),
`tests/test_codex_approver_tools.py`, `tests/test_codex_approver_push.py`,
`tests/test_codex_approver_runner.py`, `tests/test_codex_approver_archive.py`,
`tests/test_codex_approver_unmatched.py` and
`tests/test_codex_approver_wiring.py`, plus a live check of the rubric with the
real Codex on seven hand-built cases. The review record is in
`docs/plans/next.md` until archived.

## Related

- `docs/specs/codex-approver.md`
- `docs/decisions/0001-codex-reviews-with-a-prompt-only-read-boundary.md`
- `hooks/codex_approver.py`, `codex-approver/`
