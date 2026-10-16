# 0004: Remote-runner fetch

Status: Completed
Created: 2026-10-16
Completed: 2026-10-16

## Outcome

`remote-runner fetch <job> <path>... [--dest DIR] [--as NAME] [--force]` copies
named regular files from a finished job's worktree on a runner to the local
machine, so untracked outputs such as `connect4` training weights can be
retrieved without an arbitrary `scp` or `rsync`. Behavior is defined in
`docs/specs/remote-runner-fetch.md`.

## Scope

- `bin/remote-runner`: `fetch` controller action, `fetch` worker operation,
  framed stream protocol, local safe placement.
- `settings.json`: `fetch` in `permissions.ask` for every `submit` spelling.
- Tests, ADR 0003, README remote-runner section, `CLAUDE.md` policy wording
  (tracked copy and `~/.claude/CLAUDE.md`), `~/.claude` install.
- A security review of the new code, with fixes and regression tests.

## Non-goals

- Directory, glob, or recursive fetch; resume; compression.
- Fetching logs, metadata, or anything outside `worktree/`; pruned jobs.
- Pushing local files to a runner.
- Changes to job execution, provenance, or `artifacts` output.
- Editing `connect4` (a follow-up there may document the fetch step).

## Assumptions

- Spec `docs/specs/remote-runner-fetch.md` is the requirements source; this
  plan does not widen it. The spec must be accepted before implementation.
- The runner needs only Python 3 and the streamed worker script (ADR 0002
  model); no remote deployment.
- Job directories and metadata are untrusted, job-writable data.
- The permission engine matches command text; the new `ask` rules are probed
  with a harmless no-op before they are relied on.
- Owner decisions (2026-10-16): default placement is the same relative path
  under the repository root; `--dest` overrides the base directory; `--as`
  renames the basename of a single fetched file; the plan includes a security
  review.

## Constraints

- Commit and push only on explicit approval. Do not add AI attribution to
  commit messages.
- Fetched bytes are untrusted job output; the job tree and metadata are
  job-writable.

## Discovery and impact evidence

Graphify: skipped — scope is enumerated by direct reading of
`bin/remote-runner` (1328 lines: `invoke_worker` at 609, `controller` at 734,
`worker` at 1040 with the existing `artifacts` operation at 1248, parsers at
1266 and 1301), `settings.json` (`allow` has `artifacts`; `ask` has `submit`,
`cancel`, `prune` in five spellings), and the tests that parametrize those
spellings (`tests/test_permissions.py`, `tests/test_tools_security.py`,
`tests/test_remote_runner_snapshot_submit.py`). Precedent: ADR 0002.

## Completion criteria

- All acceptance criteria 1-8 of the spec pass in automated tests.
- The security review has no unresolved Critical or High findings.
- `./install.py --check` is clean after the reviewed live install.
- A live fetch of a `connect4` checkpoint from `ned` matches a local
  `sha256sum` (spec criterion 9).
- The full test suite passes.

## Increments

### Increment A — Controller argument validation and placement

Dependencies: None
Affected areas: `bin/remote-runner`, `tests/test_remote_runner_fetch.py` (new)

1. Tests first (no SSH): `--as` with several paths, or with an empty name,
   `/`, `..`, `.`, NUL, or a leading `-`, is refused; a path that is absolute,
   has `..`, an empty component, NUL, or a leading `-` is refused; more than
   16 paths is refused; `--dest` must exist; default, `--dest`, `--as`, and
   combined placement match the spec table; an existing target, a git-tracked
   target, and a symlink escaping the base are refused without `--force` (the
   symlink case also with it); all targets are validated before any write.
2. Add the `fetch` subparser and pure placement and validation helpers.

Verification: new tests.
Completion: placement and refusal rules proven without a transport.

### Increment B — Worker operation and framed stream

Dependencies: Increment A
Affected areas: `bin/remote-runner`, `tests/test_remote_runner_fetch.py`

1. Tests first with a fake `ssh` that runs the remote command locally (as in
   the snapshot submit tests): a file arrives byte-identical with a correct
   SHA-256; a non-finished job state, a symlink component, a non-regular file,
   a missing file, an over-limit file count or size, and a file that grows
   while read are refused; job state is recomputed, not trusted from metadata;
   a truncated stream, wrong digest, wrong length, unexpected name, and extra
   frame leave no file or temporary file; output carries `dut_commit`,
   `integrity`, and `untrusted_job_data`.
2. Implement the `fetch` worker operation (directory-fd `O_NOFOLLOW` opens,
   `fstat` size, bounded reads, framed stdout) and the controller reader
   (temp file in the destination directory, verify, atomic rename, mode
   `0644`, cleanup on failure).

Verification: new tests plus `tests/test_tools_security.py` and the existing
remote-runner tests.
Completion: end-to-end fetch works against the local shim; `artifacts` and
other operations are unchanged.

### Increment C — Permissions

Dependencies: Increment A
Affected areas: `settings.json`, `tests/test_permissions.py`

1. Add `remote-runner fetch` to `ask` in all five spellings used for `submit`.
2. Extend the permission tests so `fetch` is never in `allow` and is in `ask`
   in every spelling; probe the new wildcard forms with a harmless no-op and
   record the result.

Verification: `tests/test_permissions.py`; probe recorded.
Completion: every spelling prompts.

### Increment D — Security review

Dependencies: Increments B, C
Affected areas: `bin/remote-runner`, `tests/test_remote_runner_fetch.py`

1. Run the `security-review` skill on the new code: path validation and
   confinement, symlink and TOCTOU handling on both sides, frame parsing and
   size accounting, overwrite and tracked-file checks, `--dest` and `--as`
   handling, temp-file lifecycle and permissions, ssh argument construction,
   and denial-of-service via size or file count.
2. Run an independent adversarial `security-reviewer` pass in a scratch
   directory with a hostile fake worker (traversing and duplicate names,
   oversized and lying frames, symlink races, a symlinked `--dest`, a hostile
   job tree, and metadata claiming a finished state).
3. Fix each finding with a failing regression test first; record dispositions
   in the Result and in the ADR if a decision is durable.

Verification: full suite; findings and dispositions recorded.
Completion: no unresolved Critical or High findings.

### Increment E — Documentation and ADR

Dependencies: Increment D
Affected areas: `docs/decisions/0003-remote-runner-fetch.md`,
`docs/decisions/README.md`, `docs/specs/remote-runner-fetch.md`, `README.md`,
`CLAUDE.md`, `~/.claude/CLAUDE.md`

1. ADR 0003: framed stream over the worker channel rather than tar, scp, or a
   job-initiated push; `ask` permission; refusal rules.
2. README remote-runner section: `fetch` usage, examples with `--dest` and
   `--as`, limits, and cautions; set the spec status to Accepted.
3. `CLAUDE.md` (both copies): `fetch` is the way to retrieve untracked job
   output; show the wording to the owner before installing.

Verification: `git diff --check`; wording reviewed by the owner.
Completion: documents consistent with behavior.

### Increment F — Install and live verification

Dependencies: Increments D, E
Affected areas: `~/.claude`, runner `ned`, `../connect4` (read-only use)

1. Reviewed `./install.py --dry-run`, then the approved live install;
   `./install.py --check` clean.
2. With the owner's approval, `remote-runner fetch` a checkpoint from a
   finished `connect4` training job on `ned` into `../connect4`; compare the
   reported SHA-256 with a local `sha256sum`.

Verification: `./install.py --check`; hash comparison.
Completion: completion criteria met.

## Verification

- `python3 -B -m unittest discover -s tests` and
  `python3 -B -m unittest discover -s skills/graphify-workflow/tests`
  (documented in `README.md`).
- `./install.py --check` after install.
- `git diff --check` before any completion claim.

## Risks and sensitive actions

- Security-sensitive: writes remote-controlled bytes to the local disk.
  Mitigated by framed protocol, `O_NOFOLLOW`, confinement, atomic placement,
  overwrite and tracked-file refusals, size limits, and the owner prompt.
- Increment F writes into `../connect4` and uses `ned`; both need explicit
  approval at that time.
- Installing to `~/.claude` and any commit require explicit approval.

## Deferred work

- Directory and glob fetch, resume, compression.
- A `connect4` doc update describing the fetch step.

## Result

Completed 2026-10-16. Design record: ADR 0003; requirements:
`docs/specs/remote-runner-fetch.md`.

**Delivered.** `remote-runner fetch <job> <path>... [--dest DIR] [--as NAME]
[--force]` with the framed stream, safe placement, time bounds, and the five
`ask` permission spellings; tests in `tests/test_remote_runner_fetch.py`;
ADR 0003, the README section, the spec, and the `CLAUDE.md` bullet (tracked and
installed copies).

**Verification.**
- Full suite: 524 tests, 5 skipped, passing
  (`python3 -B -m unittest discover -s tests`). `git diff --check` clean.
- `./install.py --check`: "Configuration matches the tracked repository" after
  the approved install (backup in
  `~/.claude/backups/claude-global-config-20261016T113250Z`).
- Live fetch (spec criterion 9): job
  `ned--connect4--20261015-203211--ee63c620` (`PASSED`, `integrity: ok`,
  snapshot job) fetched `checkpoints/latest.pt` into
  `~/projects/connect4` with `--as ned-20261015.pt`; 925,709 bytes; local
  `shasum -a 256` equals the reported `aced7269…befc`. Existing checkpoints
  untouched, no staging leftovers.

**Security review record (Increment D).** The author's own `security-review`
pass plus three passes by an independent `security-reviewer` agent with scratch
experiments against a hostile fake runner. Every confirmed finding got a failing
regression test first.

| Source | Finding | Disposition |
|---|---|---|
| Own pass | Writes into `.git/` or `.claude/` | Fixed: `.git` never, then widened below |
| Own pass | Case-colliding names; silent partial placement; option-like path values; hidden worker reason | Fixed |
| Pass 1 F1 | `--dest` bypassed the `.git`/`.claude` guard | Fixed: whole-path name check plus git-directory file identity |
| Pass 1 F2 | Stalled runner hangs the controller | Fixed: bounded non-interactive SSH, idle watchdog |
| Pass 1 F3 | Unbounded runner stderr spooled to disk | Fixed: bounded pipe tail (4 KiB) |
| Pass 1 F4 | SIGTERM/SIGHUP stranded temp files | Fixed: handlers unwind cleanup |
| Pass 1 F5 | Tracked check bypassed by case/normalisation, failed open | Fixed: folded identity-based, fail-closed |
| Pass 1 F6 | Unicode-normalisation collisions | Fixed: NFC plus casefold duplicate check |
| Pass 1 F7 | Tracebacks on odd input | Fixed: clean refusals |
| Pass 2 N1 | Watchdog measured chunk completion, no overall cap | Fixed: per-slice progress plus size-based budget |
| Pass 2 N2 | SIGQUIT/USR1 stranded temp files | Fixed: wider signal set; SIGKILL accepted |
| Pass 2 N3 | Denylist incomplete (dot and credential names) | Fixed: any dot-prefixed component needs `--force` |
| Pass 2 N4 | Tracked check limited to the cwd repo | Fixed: destination's own repo and tracked-directory prefix |
| Pass 2 N5 | Remaining tracebacks (user expansion, byte lengths, missing git) | Fixed |
| Pass 3 M1 | Dot rule skipped for a dot-named destination repository | Fixed: dot rule judged against the working repo only |
| Pass 3 M2 | Tracked file in a nested repository | Fixed: deepest containing repository checked |
| Pass 3 race | Staging record after the file was opened | Fixed: recorded first |
| Pass 3 M3 | Dot rule blocks destinations such as `~/.cache/out` | Accepted: documented, `--force` overrides |

No Critical or High finding is unresolved. Items the reviewer marked suspected
were accepted rather than fixed: a job record falsely claiming to be finished,
and `link`/`rename` failing across filesystems (fails safely). During pass 2 a
macOS "Python quit unexpectedly" report appeared; it came from the reviewer's
deliberate SIGQUIT experiment, not from the product code.

**Unresolved risks and accepted limits.**
- A multi-file fetch that fails during placement reports what was placed and
  does not roll it back.
- `SIGKILL` can leave a `.rr-fetch-*.tmp` file in the destination base.
- Non-dot, code-adjacent names are the owner's decision at the permission
  prompt.
- Reviewed on macOS (case- and normalisation-insensitive) only; real SSH
  behavior was exercised by the single live fetch, not by the adversarial
  experiments.

**Next action.** Nothing is committed. Commit only on explicit request; a
possible follow-up in `connect4` is to document the fetch step.
