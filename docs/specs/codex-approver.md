# Codex approver: a bounded second decision-maker for owner prompts

Status: Accepted (increment 1 implemented; increments 2 and 3 pending)
Date: 2026-10-16

## Purpose

The owner is prompted for actions they already trust, chiefly
`claude-workflow commit` and `claude-workflow remove`, whose helpers enforce
their own protections. This specification defines an approver that evaluates
such a prompt in the owner's place, treating the requester as untrusted, and
lets it proceed only when fixed checks and a Codex review all pass. Anything
else leaves the normal prompt to the owner.

## Scope (version 1)

- A `PermissionRequest` command hook that sees only prompts raised by `ask`
  rules, in every permission mode including `auto`.
- A declarative rule engine: one rule file per approvable command shape.
- Two initial rules: `claude-workflow commit` and `claude-workflow remove`
  (`--confirm` form), in all five command spellings the settings already list.
- A trusted collector per rule that gathers the facts the decision rests on.
- A Codex review of those facts, through the existing Codex CLI pattern of
  `bin/ask-codex` and the prompt-only read boundary of ADR 0001.
- A local verdict log and an owner notification.
- Delivery in increments: advice-only first, `allow` authority second.

## Non-goals

- Overriding a `deny` rule or a hard-denied command. A hook `allow` does not
  satisfy a settings `deny`; this was verified by experiment (see Evidence).
- Approving `git push`, publishing, deploying, dependency installation, or
  secret use. These stay with the owner permanently. `git push` and
  `remote-runner submit|fetch|cancel|prune` are covered by advice-only logging
  (see "Advice for push and remote-runner"); any authority over them needs its
  own ADR, decided after the evidence period.
- Approving implementation of a plan increment. That is a separate later
  feature that checks a recorded owner approval in `docs/plans/next.md`.
- Judging a command from its text alone; Codex never reads the repository.
- Project-level rules that widen trust without a user-side registration
  (increment 3).
- A neutral wording in `claude_project_template` (a later module, see
  Packaging).

## Decisions (owner)

| Topic | Decision |
|---|---|
| Goal | Codex decides in the owner's place for trusted helper prompts, treating the requester as mostly untrusted |
| Authority | Advice-only first; `allow` only after the owner approves increment 2 |
| Modes | Used mostly in `auto` mode, so the hook must act on `ask`-rule prompts |
| Gate | Deterministic first, Codex second; Codex can confirm or veto, never promote |
| Facts | The gate collects them with trusted code; the requester's text is not a source |
| Extensibility | Rules are data; adding a command is a rule file plus a fixture |
| Trust scope | Global ceiling in `~/.claude`; a project may request, but a user-side hash-pinned registration is required |
| Dependency | The module requires Claude Code and the Codex CLI |

## Evidence (experiments, Claude Code 2.1.301, 2026-10-16)

1. `PermissionRequest` fires for a command that prompts in default mode, with
   `tool_name`, `tool_input`, `cwd`, `permission_mode`, `session_id`.
2. In `auto` mode it does not fire for commands the auto classifier approves.
3. In `auto` mode it fires when a settings `ask` rule raises the prompt.
4. A hook returning `behavior: allow` satisfied that `ask` rule; the command ran.
5. A hook with no decision leaves the dialog (interactive) or refuses the call
   (non-interactive).
6. A settings `deny` rule blocked the command and the hook never ran.
7. A `systemMessage` from the hook was not visible in the dialog.

8. A hook that outlives its `timeout` is killed, its output is discarded, and
   the normal permission path resumes (a hook sleeping 12 s with `timeout: 3`
   never finished, and its `allow` was ignored).
9. `codex exec -s read-only --ephemeral --ignore-user-config` answers the
   verdict schema in 3.7 to 6.5 s from an empty temporary directory (several
   models, low and medium effort). It needs `--skip-git-repo-check` there.

Not tested: the default `PermissionRequest` timeout (documented as 600 s, so
the hook sets its own), and whether the hook fires for foreground subagent
calls.

Chosen values: model `gpt-6.1-sol`, effort `medium`, Codex timeout 15 s, hook
timeout 25 s. Models were searched cheapest measured cost first against 52
hand-built cases, then re-tested after the rubric gained the
`change_is_safe_in_itself` check, on 72 cases of which 20 were written after
that change. Results:

- Old rubric: `gpt-6-luna` declined too many benign requests; `gpt-5.6-luna`
  approved a commit that skips security tests; `gpt-6.1-sol` approved a commit
  that logs the Authorization header (the rubric never asked whether the change
  itself was harmful); `gpt-6-sol` medium passed (0 of 96 bad requests approved).
- New rubric: `gpt-6.1-sol` medium approved 0 of 105 bad requests (0 of 24 on the
  held-out harmful cases, four of which are harms the rubric does not list) and
  declined 2 of 71 benign requests, p95 8.5 s, about 0.33 to 0.43 credits per
  call. `gpt-6-luna` still declined too many benign requests (5 of 28).
  `gpt-6-sol` was not re-tested under the new rubric.

`gpt-6.1-sol` was chosen because it is the only model with evidence under the
rubric that ships. It has the same published credit rates as `gpt-6-sol`. The
last repeat of its second stage was lost to the Codex usage limit, so the
result is 176 valid calls, not 216. Real review prompts took 5.0 to 10.4 s.

## Behavior

### Flow for one prompt

1. Claude Code raises `PermissionRequest` after `deny` and `ask` rules ran.
2. The engine loads the effective rules (global; later, registered project).
3. No matching rule: exit with no output; the owner sees the normal prompt.
4. The matching rule's collector runs fixed, read-only commands (for commit:
   staged paths, message, `HEAD`; for remove: the helper's preview) and never
   executes text taken from the request.
5. Deterministic checks run on the collected facts. Any failure: no decision.
6. Codex is called with the premise, the facts and the rule's rubric, under a
   short timeout (15 s). Its reply must validate against a strict schema.
7. Verdict `approve` requires every check to pass and Codex to approve.
8. The verdict is logged and notified. In increment 1 nothing else happens.
   In increment 2 an `approve` also returns `behavior: allow`.

### Rules

A rule file declares the exact command shape, argument constraints, the
collector, the deterministic checks, and the rubric. The engine contains no
per-command logic. A command with no rule is never decided.

Initial deterministic checks:

- commit: a read-only preflight that mirrors `claude-workflow commit`, which
  stages the named paths itself and accepts new untracked files. `--expected-head`
  equals the current `HEAD`; a non-empty index requires `--leave-other-staged`
  and no named path is already staged; the helper's own path and message
  validation (including its attribution refusal) passes; no path is
  credential-looking or not a regular file; no secret-looking line in the
  collected content or message (pattern and entropy based); the change is
  complete (not truncated or binary); the repository configures no filter
  driver, hook, signing program or diff program that the real commit would run
  (`repo_config_safe`, names only). Changes are computed in Python from the `HEAD` blob and the
  working-tree bytes, never through Git diff or status, so repository filters
  cannot run.
- remove facts include each target's size, entry count (bounded) and
  ignored status.
- remove: every path relative and inside the repository; none is Git
  metadata; `--confirm` is present; the gate's own fresh preview of exactly
  these arguments is clean and lists the same paths. The helper keeps no
  preview receipt, so the gate does not claim the owner previously ran the
  preview; the helper revalidates when it executes.
- Both: the command resolves, as the shell would, to the installed helper
  under an interpreter that is not inside the repository. An empty or relative
  `PATH` entry declines only when it actually holds the executable.

### Advice for push and remote-runner

Five further rules log advice only, for `git push`, `remote-runner submit`, `fetch`, `cancel` and `prune`, and `ask-codex archive`
(`git` matches only the bare word; `remote-runner` and `ask-codex` in the five spellings the settings list). They exist to measure
how often Codex and the owner agree, as `--report` shows per rule. Their collectors use local files and Git state
only: no SSH, no `remote-runner status`, no `git ls-remote`, and no network. Facts about the remote's current state
(whether a job exists or runs, what the remote branch holds) are absent, and each rubric section says so.

- push: the effective refspecs after applying the owner's Git configuration (`push.default`, `remote.<r>.push`,
  `branch.<b>.pushRemote`, `remote.pushDefault`), the effective push URL host without credentials, and the commits,
  paths and diff on no remote-tracking branch of that remote as of its last fetch. Deterministic checks decline a
  force or `+` refspec, mirror, delete, tag push, a URL or unconfigured name as the remote, an unusual transport or
  embedded credentials, an unresolvable or wildcard target, secret-looking or credential-path content, an incomplete
  diff, and any program the push would run (hooks, credential helper, `core.sshCommand`, and so on).
- submit: exactly one of `--remote` (configured) or `--best`; `--ref` and `--snapshot` exclusive; the profile exists in
  the runner contract of the revision that runs (the working tree's for `--snapshot`); the revision is on an `origin`
  branch as of the last fetch; origin is an ordinary https or ssh URL without credentials.
- fetch: a well-formed job on a configured remote; plain unique job-relative paths (at most 16); no `--force`; each
  local target is not git metadata, dot-prefixed, behind a link, existing, or tracked.
- cancel: a well-formed job on a configured remote that belongs to this repository's project.
- prune: a configured remote and finite, non-negative retention periods; `--apply` and shortened retention are facts
  for the reviewer.

- archive: `ask-codex archive [--plan <file>]` closes a plan review. The collector runs the installed
  `ask-codex status`, a local read-only command that verifies the review state's seal itself, under the hardened Git
  environment with a timeout and an output cap, and keeps rounds used, the bound, any block, owner grants, `closed`
  and the ids of undecided blocker or major findings. The hook never reads the seal key or the round files. A missing
  or unverifiable review state declines; an unfinished review is a fact for the reviewer.

None of these rules approves anything. The hook still prints no decision.

### Codex rubric

The premise states that the command, arguments, message and file contents are
authored by a party that may intend harm, and that nothing in them is an
instruction to the reviewer. The reviewer decides only from the supplied facts
and the rule's named checks, answers `approve` only if every check passes, and
otherwise answers `decline` naming the failed check IDs. The reply is strict
JSON. The exact wording is part of the plan and is tested against hostile
fixtures.

### Failure behavior

Any error, timeout, Codex outage, schema violation or unexpected input yields
no decision. The owner sees the normal prompt (or, non-interactively, the
call is refused as it is today).

### Log and notification

The log is local, append-only and unmirrored: timestamp, rule, facts digest,
check results, Codex verdict, reason. It may contain commit messages and is
never committed. A short notification line reports the verdict. The log is the
evidence used to decide whether to enable increment 2.


### Outcomes and the agreement report

A prompt that appears gets a verdict, but the log does not say what the owner answered. `PostToolUse` and
`PostToolUseFailure` hooks, filtered by `if` to exactly the covered command spellings, record whether the command then
ran: rule, a digest of the command, session id, tool use id, `ran` or `ran_failed`, exit code and duration, in
`outcomes.jsonl`. The tool's output is never read into the log. A refused or abandoned prompt produces no event, and
that absence is the signal that the owner (or the session) did not run it.

`python3 ~/.claude/hooks/codex_approver.py --report [--days N]` pairs each verdict with the outcome of the same command
in the same session within 30 minutes and prints a verdict-by-outcome table, the agreement rate (approve then ran,
decline then not run), the disagreements with their reasons, and runs that had no prompt. Prompts younger than 30
minutes are counted as awaiting an answer. The report is the evidence for deciding on increment 2.

## Increments

The increments below are the original delivery order. Advice for push and remote-runner was added later without
changing them.

1. Engine, two rules, collectors, Codex call, log, notification; advice-only.
2. `allow` for the two rules, after the owner approves it; ADR; mirrored
   `CLAUDE.md` and `settings.json` changes.
3. Project requests with a user-side registry that pins the project file's
   hash; classes beyond the first two; any edit drops back to no decision.

## Packaging

Install from `claude_global_config` like `ask-codex`. A later module in
`claude_project_template` must declare `requires` on the `claude` and `codex`
modules and state the Claude Code dependency in its documentation.

## Acceptance criteria

1. A matching, valid commit or remove prompt produces a logged verdict and a
   notification, and no `allow`, in increment 1.
2. A command with no rule, and a command failing any deterministic check,
   produce no decision and no Codex call.
3. Codex timeout, outage, non-JSON, wrong schema or a missing check ID
   produce no decision.
4. A Codex `approve` never changes a deterministic failure into an approval.
5. Hostile fixtures (instructions in a commit message or filename, a symlinked
   path, a credential-looking file, a stale `HEAD`, a preview that differs
   from the arguments) never produce `approve`.
6. A `deny` rule is never bypassed; adding a rule requires only a rule file and
   a fixture.
7. The hook declares its own short timeout and returns within it.
8. In increment 2, only the two rules can return `allow`, and the owner's
   approval and policy change are recorded in an ADR.
9. The security review passes (adversarial probes of every boundary above).
10. A live check in `auto` mode shows an `ask`-tier commit or remove prompt
    receiving a logged verdict.

## Accepted risks

- Codex is a second check, not the safety floor; the deterministic gate is.
- The facts could change between approval and execution; checks bind to
  `HEAD` and the exact command, and the helpers revalidate.
- The hook runs outside any sandbox and is trusted code.
- The log may hold commit messages; it stays local.
- Behavior was observed only on macOS and Claude Code 2.1.301.

## Related

- `docs/specs/second-opinion-plan-review.md`
- `docs/decisions/0001-codex-reviews-with-a-prompt-only-read-boundary.md`
- `hooks/review_agent_guard.py`, `bin/ask-codex`
