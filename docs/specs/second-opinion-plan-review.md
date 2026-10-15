# Second opinion: bounded Codex review of implementation plans

Status: Accepted (2026-10-15); implemented and verified; see ADR 0001
Date: 2026-10-15

## Purpose

The owner reviews implementation plans by hand-copying them between Claude Code
and the ChatGPT/Codex application until both agree. This specification defines
a helper and skill that run that loop from Claude Code, using the owner's
ChatGPT subscription through the Codex CLI (no API key, no per-token billing),
with a hard bound on rounds and Claude as the only writer of the plan.

## Scope (version 1)

- One review kind: **plan review** of `docs/plans/next.md`.
- On-demand only: the owner asks for a Codex review of the plan, or invokes
  `/second-opinion`. Nothing fires automatically.
- A helper CLI `ask-codex` and a skill `second-opinion`, both installed from
  `claude_global_config`.

## Non-goals

- Automatic triggers, scheduling, or hooks.
- Other review kinds (diff review, free-form question). The design must not
  prevent them; see Extensibility.
- Codex writing to any file. Codex is read-only.
- Replacing the owner's approval of a plan or of implementation.
- A neutral wording of this capability in `claude_project_template`.
- Pre-commit enforcement of identity or of review state.

## Decisions (owner)

| Topic | Decision |
|---|---|
| Use case | Plan review loop between Claude and Codex |
| Who writes | Claude only; Codex is read-only and returns suggestions |
| Convergence | A round with no blocker or major finding |
| Meaningful severities | `blocker`, `major`; `minor` and `nit` never block |
| Bound | Default 3 Codex reviews, per-request override, hard ceiling 5 |
| Beyond the bound | Owner input via `extend`/`reset`, enforced by a permission prompt |
| After convergence | Claude stops and reports; the plan stays `Proposed` |
| Opt-in | A request that explicitly says to implement on agreement authorizes it |
| Context across rounds | Fresh Codex session each round plus a ledger in the prompt |
| State | Local, untracked `.debug/<date>-plan-review/`; the helper owns the counter |
| Cleanup | `archive` captures a summary into the archived plan and closes the review; `prune` previews then confirms, 14-day retention, never automatic |
| Visibility | Whole repository, read-only; boundary is prompt-only (accepted) |
| Output | Structured JSON via `--output-schema` |
| Disagreement | Claude may reject with a reason; a second re-raise escalates to the owner |
| Failures | One automatic retry, 10-minute timeout, stop after 2 consecutive failures |
| Model | `gpt-6.1-sol`, explicit, `high` effort, ceiling `xhigh`; calibration step |
| Names | `ask-codex`, `second-opinion`, `.debug/<date>-plan-review/` |

## Behavior

### The loop

1. Claude writes or updates the plan (`Status: Proposed`).
2. `ask-codex review-plan` runs one Codex round and returns structured findings.
3. For every **blocker** and **major** finding Claude records a decision with
   `ask-codex decide <id> applied|rejected [--reason ...]`, editing only
   `docs/plans/next.md` for applied findings. Claude may also apply or reject
   minor and nit findings. Findings about anything outside the plan are
   reported to the owner and never acted on.
4. The next round's prompt includes the ledger (applied findings, and rejected
   findings with reasons). Codex may re-raise a rejected finding only by citing
   its ledger ID and supplying new evidence.
5. The loop ends at the first stop condition below.

### Stop conditions (enforced by the helper)

| Condition | Result |
|---|---|
| Round returns no blocker or major finding | **Converged.** Claude stops and reports rounds used and a short summary. Plan stays `Proposed`. |
| Rounds used reaches the bound | Stop and ask the owner what is still disputed. |
| Codex re-raises a rejected finding a second time | Stop and escalate to the owner. |
| 2 consecutive failures | Stop and report the error and fix. |
| Not signed in, usage limit, model unavailable | Stop immediately; never retried. |

The bound counts completed Codex reviews, not attempts. A failed attempt never
consumes a round.

### Owner input

Continuing past the bound requires `ask-codex extend <K>` (1–5 rounds, one
grant at most 5) or `ask-codex reset`. Both are listed in `permissions.ask` in
`settings.json`, so Claude Code prompts the owner before they run, including in
auto mode. Each grant is recorded in `state.json` with a timestamp. The skill
forbids Claude from running either command except in direct response to the
owner's explicit request.

### Opt-in implementation

By default Claude never starts implementation after convergence. If the owner's
request explicitly says to implement when Claude and Codex agree, Claude may
proceed after convergence and records that authorization in the plan.

### Escalating effort

Effort starts at `high`. It rises to `xhigh` (the ceiling) for the **next**
round when either a rejected finding is re-raised once, or the same blocker or
major finding appears in two consecutive rounds, or the round number reaches 3.
Once raised it stays raised for that plan's loop. The report states when and
why it changed. A per-request `--effort` override is never persisted and may
not exceed the configured ceiling.

## Components

### `ask-codex` (`bin/ask-codex`, Python 3.9, standard library only)

| Command | Purpose | Gate |
|---|---|---|
| `review-plan [--plan PATH] [--max-rounds N] [--model M] [--effort E]` | Run one round | refuses while a previous blocker or major has no decision |
| `decide <finding-id> applied\|rejected [--reason TEXT]` | Record a decision | none; a rejection requires `--reason` |
| `status` | Rounds, bound, effort, failures, grants, model validity | none |
| `models` | List the models and efforts Codex currently offers | none |
| `archive` | Print a compact review summary and mark the review closed | permission prompt |
| `prune [--confirm]` | Preview, then delete, closed review directories past retention | permission prompt (both forms) |
| `extend <K>` | Add 1–5 rounds | permission prompt |
| `reset` | Clear the counter and effort escalation | permission prompt |

Exit codes: 0 success, 1 not converged or stopped by a condition above, 2 usage
or fatal error.

### Archiving and cleanup

Review state is never deleted automatically.

- **`archive`** is run when the plan is archived. It prints rounds used, the
  model and effort of each round, any escalation and why, and every rejected
  finding with its reason. Claude pastes this into the archived plan's
  `Result`, so the durable record lives in git with the plan. It then marks the
  state `closed` with a timestamp; a closed review accepts no further rounds,
  `extend`, or `decide`.
- **`prune`** with no flag is a preview: it lists closed review directories
  older than `prune_retention_days` (default 14, counted from the close
  timestamp) and deletes nothing. Rerunning the identical command with
  `--confirm` deletes exactly the listed directories.
- Only directories matching `.debug/*-plan-review/` that contain a `state.json`
  marked `closed` are eligible. Open reviews, including a converged review that
  has not been archived, are never pruned. Symlinks are never followed and
  anything outside the repository's `.debug/` is refused.

### Implementation notes (Increments B–C)

Refinements made while building; they supersede the wording above where they
differ.

- **Output and exit codes.** Every command prints one JSON object. Exit 0 means
  the command succeeded, including a review round that returned findings
  (`outcome` is `converged` or `changes_needed`). Exit 1 means a stop condition
  fired (`status: "stopped"` with a `reason`: `bound_reached`,
  `reraise_escalation`, `failure_cap`). Exit 2 is a usage or fatal error
  (`status: "error"` with a `reason` and, where one exists, a `fix`).
- **`init`** is a public subcommand that prepares state without calling Codex.
- **State directories** are `<date>-plan-review`, with `-2`, `-3`, … appended
  when two plans start on the same day. Prune therefore matches
  `.debug/*-plan-review*/`.
- **`--max-rounds`** is accepted only when a review starts (no rounds used yet).
  After that, the bound changes only through `extend`. Values above the ceiling
  are clamped to it with a warning.
- **Relative `--plan` paths** resolve against the repository root.
- **Failure counting.** Each failed attempt (including the automatic retry)
  increments a persisted counter; a completed round resets it. When the counter
  reaches `max_consecutive_failures` the run stops with `failure_cap`. A later
  invocation while at the cap makes a single attempt with no retry.
- **Re-raise escalation** blocks the review (`blocked` in `state.json`) until
  the owner runs `extend` or `reset`.
- **Same-finding detection** across consecutive rounds compares a normalized
  location and problem text; it is a heuristic. A re-raise that cites a ledger
  ID is always detected exactly.
- **`extend K`** adds K rounds (1–5) to the current bound, and after it at most
  5 rounds may remain, so grants cannot stack into an open-ended loop. It also
  clears a re-raise block.
- **`reset`** keeps the round history and ledger (finding IDs stay unique). It
  opens a fresh window of `rounds_default` rounds from the current round,
  returns effort to the default, restarts the round-3 effort floor from that
  point, and clears failures and any block. Each use is recorded in `grants`.
- **`archive`** resolves the active plan, so run it before the plan itself is
  archived and `next.md` is reset. It is idempotent.
- **`prune`** does not need an active plan. A directory is skipped, with a
  reason, unless `state.json` is readable and closed past retention and the
  directory holds only the helper's own files; a symlink is never followed.
  `--confirm` recomputes the same list, so it deletes exactly what the
  preview of the same moment shows.
- **State integrity (security review).** `state.json` carries an HMAC `_seal`
  keyed by a per-machine `.seal-key` (mode 0600, created on first write), and
  each round file is pinned by a SHA-256 in `state.round_digests`. A state or
  round file changed outside the helper is refused (`reason: tampered`) and
  never reset. This is tamper-**evidence** against accidental edits and
  injected instructions; it is not a boundary, because the key is readable by
  the same account.
- **Plan identity (security review).** An open review belongs to its plan
  **file**, so editing the title or `Created:` line cannot open a fresh review
  and reset the bound; the helper warns that the identity changed. A closed
  review is matched only by exact identity, so a new plan can start after
  `archive`.
- **Input hardening (security review).** Model names must match
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$`; plan paths with control characters are
  refused; `.debug` as a symlink is refused; the lock file is opened without
  following links; Codex output is capped at 1 MiB, 100 findings, and 4000
  characters per text field; every other error ends in `status: error`, never
  a traceback.
- **Executables (independent review).** `codex` and `git` are resolved only
  from absolute `PATH` entries that are outside the repository (and, for git,
  outside the working tree); empty, `.`, and relative entries are ignored, so
  a repository cannot supply its own `codex`. Codex receives the same filtered
  `PATH`. After a timeout kill, the helper waits at most 5 seconds for the
  pipes, so a grandchild that escaped the process group cannot block it.
- **Plan identity, continued.** An open review also matches by `samefile` (other
  spellings of the path on case-insensitive filesystems, hard links) and by
  plan identity (a copy with the same title and `Created:`). First starts take
  a `.debug/.lock`, so concurrent starts create one review. Single-line
  fields (problem, location, reason) are collapsed before they enter the
  ledger or the next prompt, so a finding cannot forge ledger lines.
- **Second review fixes.** `archive` records the plan identity the file has at
  that moment (`closed_keys`), so retitling before `archive` cannot reopen a
  fresh review. `git` is resolved outside the nearest ancestor holding `.git`
  (not just the cwd tree), containment tests use `samefile` on every ancestor
  (case-insensitive filesystems) and resolve symlinked executables, a Codex run
  that finished normally is not reported as a timeout because a leftover
  process holds the pipes, the first-start lock waits at most 10 seconds, the
  seal key is created atomically and validated before any state is created, and
  state and finding identifiers match ASCII digits only. When another open
  review in the repository has used its full bound, a new review in the same
  repository carries a warning (a copied and retitled plan is otherwise
  indistinguishable from a new plan).
- **Findings are untrusted.** The skill treats finding text as data from another
  model: it must not follow instructions in a finding and must never edit
  files under `.debug/`.
- **Prompt** is read from the kind's `prompt.md` with `{{ROUND}}`,
  `{{PLAN_PATH}}`, and `{{LEDGER}}` substituted, and sent on stdin.

### State (local, untracked)

`.debug/<YYYY-MM-DD>-plan-review/` under the repository root, holding:

- `state.json` — plan key, rounds used, bound, effort, consecutive failures,
  grants, model and effort used per round, and `closed` (null or a timestamp).
- `ledger.md` — human-readable decisions.
- `round-N.json` — raw structured Codex output, token usage, timings.

The plan key is a hash of the plan's first heading and its `Created:` line, so
a new plan starts at round 0. The helper appends `/.debug/` to
`.git/info/exclude` when missing and reports it. State is written atomically.
A lock file prevents concurrent rounds. A corrupt or unreadable `state.json` is
an error, never silently reset.

### Configuration (`~/.claude/ask-codex/config.json`, tracked)

`model`, `effort_default` (`high`), `effort_ceiling` (`xhigh`),
`rounds_default` (3), `rounds_ceiling` (5), `timeout_seconds` (600),
`retries` (1), `max_consecutive_failures` (2), `prune_retention_days` (14).
There is no fallback model:
missing or invalid configuration is a fatal error.

### Review kinds (extensibility)

Each kind is a directory,
`~/.claude/ask-codex/kinds/<kind>/{kind.json, prompt.md, schema.json}`.
`kind.json` declares whether the kind uses the loop, ledger, and bound. Adding
a kind adds a directory and registers one subcommand; the Codex runner, state,
counter, and failure handling are shared.

### Skill (`skills/second-opinion/SKILL.md`)

Triggers on requests such as "have Codex review the plan" and on
`/second-opinion`. It instructs Claude on the loop, how to decide each finding,
the report format, the edit-only-`next.md` rule, the opt-in rule, and the ban on
running `extend` or `reset` unprompted.

### Installer and settings

- `config-manifest.txt` gains the helper, configuration, kind files, and skill.
- `install.py` links `ask-codex` into `~/.local/bin` alongside the existing
  helpers.
- `settings.json`: `permissions.allow` gains `ask-codex review-plan`,
  `decide`, `status`, `models`, `init`; `permissions.ask` gains `extend`,
  `reset`, `archive`, and `prune` (the whole subcommand, so the preview and the confirmed
  deletion both prompt regardless of argument order). These keys are strict
  under `settings-policy.txt`.

## Codex invocation contract

```
codex exec -s read-only --ephemeral --ignore-user-config --json \
  -m <model> -c 'model_reasoning_effort="<effort>"' \
  --output-schema <schema.json> -o <round output> -C <repo> - < prompt
```

- stdin is the prompt or `/dev/null`; it is never left open (an open stdin
  makes `codex exec` wait, verified).
- The environment is minimal: `PATH`, `HOME`, `CODEX_HOME`, `LANG`, `TERM`.
  No other variables from the owner's shell reach Codex.
- `--ignore-user-config` keeps Codex from loading the owner's MCP servers and
  plugins; authentication still uses `CODEX_HOME` (verified).
- Model and effort are always passed explicitly and never inherited.
- A timeout kills the whole process group.

## Findings schema

Top level: `summary` (string), `verdict` (informational; the helper recomputes
it), `findings` (array). Each finding: `severity`
(`blocker|major|minor|nit`), `location` (plan heading or line), `problem`,
`suggestion`, `reraises` (ledger finding ID or null), `new_evidence` (string,
required and non-empty when `reraises` is set). A re-raise without new evidence
is suppressed: it is recorded, does not block, and is not counted.

## Model policy and deprecation protection

- The default is `gpt-6.1-sol` at `high`; the ceiling is `xhigh`. `max` and
  `ultra` are never used (`ultra` delegates tasks).
- Before each run the helper validates the configured model and effort against
  Codex's own catalogue (`~/.codex/models_cache.json`): it must exist, be
  visible, support the effort, and report any `upgrade` target. A failure stops
  the run and names the replacement. The helper never switches model silently.
- The catalogue is an internal Codex file. If it is unreadable the helper warns
  and attempts the run; a "model unavailable" error from Codex is then fatal and
  non-retryable.
- Token usage and timings are recorded per round.
- **Calibration:** after the helper works, run one or two archived plans through
  `gpt-6.1-sol` and `gpt-6-astra`, both at `high`, as single rounds. Compare real
  findings, false blockers and majors, tokens, and wall time, and pin the
  default from that result. Cost on a ChatGPT plan is allowance, not dollars.

## Failure handling and integrity

| Class | Examples | Behavior |
|---|---|---|
| Transient | network error, timeout, schema-invalid output | one retry; stop after 2 consecutive failures; no round consumed |
| Fatal with a fix | not signed in, usage limit, model unavailable, effort unsupported, missing config | stop at once; say what to do |
| State | corrupt state, concurrent run, plan missing or empty | refuse; never reset silently |

- The helper recomputes convergence from the findings.
- The plan path must resolve inside the repository with no symlink escape.
- The next round refuses to run while a blocker or major lacks a decision.
- All output has control characters escaped.

## Security and privacy

- Everything Codex reads is sent to OpenAI. The owner chose, knowingly, to give
  Codex read-only access to the whole repository on the live working tree.
- **Accepted risk:** `-s read-only` prevents writes but was verified not to
  prevent reads outside the working directory. Codex can read any file the
  owner's account can read, including ignored files such as `.env`. The only
  boundary is the prompt. This is not enforced by the sandbox.
- Mitigations kept: minimal environment, closed stdin, no user config (no MCP
  servers or plugins), `--ephemeral`, read-only sandbox, and the extend and
  reset prompts.
- No secrets belong in a plan. The skill instructs Claude not to place
  credentials in the plan or the ledger.
- The helper executes only `codex`, with fixed argument lists and no shell.

## Calibration result (Increment G, 2026-10-15)

One archived plan (`docs/plans/0001-install-py-and-settings-policy.md`) was
reviewed once by each model at `high` effort, each in its own local clone of
`claude_global_config` at `a9ac24c`.

| | `gpt-6.1-sol` | `gpt-6-astra` |
|---|---|---|
| Findings | 1 major | 1 major |
| Same finding? | yes: the plan and README claim a key removed from the repository stays installed, which `install.py` and its test contradict | yes |
| Real or false? | real (verified against the code and `test_unexpected_local_key_fails_check_and_is_dropped_on_install`) | real |
| False blockers or majors | 0 | 0 |
| Input tokens (cached) | 176k (126k) | 191k (141k) |
| Output tokens | 1.7k | 1.3k |
| Wall time | not captured | 59 s |

The two models agreed. The more expensive tier showed no advantage on this
sample, so `gpt-6.1-sol` at `high` stays the default. One plan and one round is
a small sample; use `--model gpt-6-astra` per request when a plan is
high-stakes, and repeat the comparison if reviews start missing problems. The
review also corrected a real documentation error in the README.

## Accepted residual risks

Recorded after the independent adversarial review. All run as one user, so
every bound here is a guardrail against mistakes and misled instructions, not a
security boundary against a deliberately hostile same-user process.

| Risk | Why it is accepted |
|---|---|
| `--max-rounds` up to 5 at the start of a review raises the default without an owner prompt | It is the owner's design: a per-request override with a hard ceiling of 5. The skill says to pass it only when the owner asks. |
| State can be rolled back, deleted, or re-seeded (an old valid `state.json`, deleting `.debug`) and the seal key is readable by the same account | A freshness mark outside the repository is editable by the same user too. Detection of accidental or injected edits is the goal. |
| The `ask` rules match command text. Other spellings (`$HOME/...`, absolute paths, `python3 -I`, `sh -c`, `env`, `cd ... && ./ask-codex`) are not matched, and allowed test runners execute repository code | The helper cannot tell a human from Claude. A `/dev/tty` confirmation for `extend`, `reset`, and `prune --confirm` is the stronger option the owner may adopt later. |
| A planted or corrupt `.debug/*-plan-review*/state.json` makes reviews in that repository refuse until it is removed | It fails safe: the helper never acts on state it cannot verify. |
| Codex, read-only, can read files the account can read, including `.seal-key` and its own credentials | Already accepted: the boundary is the prompt, not the sandbox. |
| Nothing authenticates Codex: a `codex` earlier on an absolute `PATH` entry outside the repository is trusted | `PATH` entries inside the repository and relative or empty entries are ignored; trusting the owner's own `PATH` is inherent. |

## Acceptance criteria

1. With a fake `codex`, tests prove: the bound and ceiling; `extend` limits;
   refusal with undecided findings; convergence; re-raise suppression and
   escalation; effort escalation; retry, timeout, and failure cap; environment
   scrubbing; closed stdin; exact Codex arguments.
1a. `archive` prints the summary and closes the review, and a closed review
   rejects `review-plan`, `decide`, and `extend`. `prune` previews without
   deleting; `--confirm` deletes only closed directories older than the
   retention period, never open ones, symlinks, or paths outside `.debug/`.
2. Catalogue validation behaves correctly for a listed model, a hidden model, a
   missing model, an unsupported effort, and an unreadable catalogue.
3. A real run against Codex succeeds with `--ignore-user-config` and
   `--output-schema` producing valid JSON.
4. The installer places the manifest entries and links `ask-codex`; `--check`
   reports no drift; the two gated commands are in `permissions.ask`.
5. A security review and an independent adversarial pass report no unresolved
   Critical or High findings.
6. The calibration comparison is recorded and the default model is pinned.
7. A real plan-review session on a throwaway plan converges, or stops at the
   bound with the report described above.

## Verified Codex behavior (Increment A, Codex CLI 0.162.1, 2026-10-15)

Each item was run in a scratch directory with `--ignore-user-config -s read-only
--ephemeral`, stdin from `/dev/null`.

| Item | Result |
|---|---|
| `--ignore-user-config` and authentication | Still authenticates with the ChatGPT login (exit 0 with an explicit `-m gpt-6.1-sol`, effort `high`). |
| `--output-schema` with `-o` | The `-o` file contains only the final message as valid JSON matching the schema. It equals the `agent_message` text in `--json` mode. |
| Strict schema | The API enforces strict mode: every object needs `additionalProperties: false` and all properties listed in `required`; optional values must be nullable (`["string","null"]`). A violating schema fails with exit 1, an `invalid_json_schema` error, and no `-o` file. |
| Token usage | With `--json`, the `turn.completed` event has `usage` (`input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`). Without `--json` only a total appears at the end of stderr. `--json` combines with `--output-schema` and `-o`. |
| Event stream | `--json` emits JSONL: `thread.started`, `turn.started`, `item.started`, `item.completed`, `turn.completed`. |
| Unknown model | Exit 1; no client-side validation. stderr has `ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error","message":"The '<model>' model is not supported when using Codex with a ChatGPT account."}}`. |
| Unsupported effort | Exit 1; `invalid_request_error`, message lists the supported values: `none, minimal, low, medium, high, xhigh, max`. (`ultra` is in the catalogue but not in this API list.) |
| stdin | An open stdin makes `codex exec` wait; `/dev/null` works. `Reading additional input from stdin...` is still printed and is harmless. |
| Cost scale | A one-page plan review used about 16k–28k total tokens including about 13k of fixed prompt overhead; a trivial prompt used about 9.7k. |

Consequences for the helper:

- Run with `--json` so token usage is captured from `turn.completed`.
- All API-level failures exit 1, so the helper classifies them by parsing the
  `ERROR: {...}` JSON in stderr (`status`, `error.type`, `error.code`,
  `error.message`) and not by exit code.
- Validate model and effort before the call (catalogue plus the list above) so
  a bad value never reaches the API.
- The schema in `kinds/plan-review/schema.json` must be strict: all fields
  required, `additionalProperties: false`, optional fields nullable.

### Not verified (cannot be triggered safely)

- The exact messages for "not signed in" and "usage limit reached". The helper
  will classify HTTP 401 and 429 and common phrases as fatal-with-fix, and the
  fake-`codex` tests will cover them with fixtures. Increment G confirms
  behavior against any real occurrence.

## Related

- `docs/plans/0001-install-py-and-settings-policy.md` — installer and settings
  policy the new entries rely on.
- `settings-policy.txt` — `permissions` is strict.
