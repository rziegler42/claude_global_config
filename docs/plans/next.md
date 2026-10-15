# Next plan

Status: In Progress (Increment G: installed, probes pending a fresh session, ned job pending)
Created: 2026-10-15

## Goal

Make remote testing of uncommitted work automatic and safe, and make approval
for outward actions structural instead of dependent on model judgment:

1. A documented security review of the two helpers that have never had one on
   record, `bin/remote-runner` and `bin/claude-workflow`.
2. `remote-runner submit --snapshot`: send a snapshot of the working tree to a
   runner as a git bundle over the existing SSH channel, with no commit, push,
   branch, or change to the local index or working tree.
3. A revised permission set in `settings.json` and matching policy wording in
   `CLAUDE.md`.

## Scope

- `bin/remote-runner`: snapshot builder, bundle transport, `submit-snapshot`
  worker action, provenance fields, prune cleanup.
- Security review (and fixes with regression tests) of `bin/remote-runner`,
  `bin/claude-workflow` including the Graphify scripts it invokes, and the agent
  guard `hooks/review_agent_guard.py`. `install.py` and `bin/ask-codex` were
  reviewed earlier and are out of scope.
- `settings.json` permissions: safe read and local-write `allow`, outward and
  irreversible `ask`, secret-path `deny`.
- Policy text in `CLAUDE.md` (tracked copy and `~/.claude/CLAUDE.md`) and the
  README remote-runner section.
- Tests, an ADR for snapshot submission, and a reviewed live install.

## Non-goals

- Pushing anything to `origin` or creating WIP branches (snapshot replaces
  that flow).
- Incremental bundles, submodule support, or downloading artifacts.
- Changing the default behavior of `submit` (a pushed ref stays the default).
- Allowing `git push` or `git commit` without a prompt.

## Assumptions and constraints

- `remote-runner` streams its own worker script over SSH, so no remote
  deployment is needed; the runner needs Python 3, Git, Bash, and the project
  toolchain.
- The configured runner is `ned` (`rziegler@ned.tpv.lan`, Ubuntu on WSL).
- The permission engine matches command text; wildcard forms are verified with
  harmless no-op probes before a rule is relied on.
- A snapshot job still records `dut_commit` and `dut_clean`; the snapshot commit
  exists only in the bundle and in the runner's cache until pruned.
- Snapshot commits use a fixed identity (`remote-runner <noreply>`), never the
  owner's git identity.
- Commit and push only on explicit approval.
- Owner decisions (2026-10-15): `remote-runner submit` prompts once per job;
  `CLAUDE.md` wording is shown to the owner before install; one real snapshot
  job on `ned` is allowed in Increment G; the Increment A scope includes the
  agent guard hook.

## Discovery and impact evidence

Graphify: skipped — scope enumerated by direct reading of `bin/remote-runner`
(629 lines: controller, `invoke_worker`, `worker`, `prune_worker`),
`settings.json`, `CLAUDE.md`, and the README remote-runner section; the
affected tests are `tests/test_tools_security.py` and `tests/test_install.py`.
Findings from the permission probes (2026-10-15): the deny rules are
literal-prefix, `git push --dry-run` and `git commit --dry-run` ran without a
prompt, and `claude-workflow commit:*` is currently allowed.

## Completion criteria

- A security review record exists for both helpers, with no unresolved
  Critical or High findings.
- `remote-runner submit --snapshot` runs a job on a runner from uncommitted
  work without touching the local branch, index, or working tree, and the job
  status shows the snapshot `dut_commit`, `dut_clean: true`, and the base
  commit.
- `settings.json` has the revised rules, `./install.py --check` is clean after
  the reviewed live install, and `git push`/`git commit` prompt.
- `CLAUDE.md` (both copies) describes the snapshot flow and its provenance
  rule.
- The full test suite passes.

## Increments

### Increment A — Security review of the existing helpers

Dependencies: None
Affected areas: `bin/remote-runner`, `bin/claude-workflow`,
`skills/graphify-workflow/scripts/`, `hooks/review_agent_guard.py`,
`tests/test_tools_security.py`, `tests/test_agent_guard.py`

1. Run the `security-review` skill on both helpers: subprocess and ssh
   argument construction, path and symlink handling, `remove` and `commit`
   guards, base64 transport, worker trust in job metadata, retention cleanup.
2. Run an independent adversarial `security-reviewer` pass with scratch
   experiments (fake `ssh`, throwaway repositories).
3. Fix each finding with a failing regression test first; record dispositions
   in the plan's Result and as an ADR if a decision is durable.

Verification: full suite; findings and dispositions recorded.
Completion: no unresolved Critical or High findings.

### Increment B — Permission set and probes

Dependencies: Increment A
Affected areas: `settings.json`, `tests/test_permissions.py` (new)

1. `allow`: read-only git (`ls-files`, `blame`, `describe`, `remote -v`,
   `tag --list`, `stash list`, `worktree list`, `branch --list`),
   `git add`, `git mv`, and `remote-runner remotes|recommend|status|log|artifacts`.
2. `ask`: `git commit`, `git push`, `git tag`, `git switch`, `git stash`,
   `claude-workflow commit|amend-message|remove` (moving `commit` out of
   `allow`), `remote-runner submit|cancel|prune`, `gh`, `ssh`, `scp`, `rsync`,
   and package installs.
3. `deny`: `Read` of `~/.ssh/**`, `~/.aws/**`, `~/.config/gh/**`,
   `~/.codex/auth.json`, and `.env` files in any directory; `rmdir`, `unlink`,
   `shred`.
4. Tests assert that `git push` and `git commit` are never in `allow`, that
   each outward action is in `ask`, and that secret paths are denied; probe
   each new wildcard form with a harmless no-op before relying on it.

Verification: tests; probe results recorded.
Completion: rules present and probed.

### Increment C — Snapshot builder

Dependencies: Increment A
Affected areas: `bin/remote-runner`, `tests/test_remote_runner_snapshot.py` (new)

1. Tests first in throwaway repositories: ignored files are excluded;
   modified, new, and deleted files are included; the index, `HEAD`,
   branches, stash, and working tree are untouched; no hooks run; unborn
   `HEAD`, size cap, and private-key and credential-file patterns are refused
   with the path reported (never the content); the contract is read from the
   snapshot.
2. Implement with a temporary index file and `git commit-tree`, with a fixed
   author and committer identity.

Verification: new tests.
Completion: a snapshot commit can be built and inspected locally.

### Increment D — Bundle transport and worker action

Dependencies: Increment C
Affected areas: `bin/remote-runner`, `tests/test_remote_runner_snapshot.py`

1. Tests first with a fake `ssh` that runs the remote command locally: the
   bundle arrives intact; bounded reads; a corrupt bundle, an oversized bundle,
   and a commit mismatch are rejected; provenance fields (`snapshot`,
   `base_commit`, `dut_commit`, `dut_clean`) are recorded; prune removes the
   snapshot ref, bundle, and worktree; non-snapshot submit is unchanged.
2. Implement a bootstrap that reads exactly the script length from stdin and
   leaves the rest as the bundle; add `submit --snapshot` (exclusive with
   `--ref`) and the `submit-snapshot` worker action.

Verification: tests, including the existing remote-runner security tests.
Completion: end-to-end submit works against the local shim.

### Increment E — Documentation and policy

Dependencies: Increment D
Affected areas: `README.md`, `CLAUDE.md`, `~/.claude/CLAUDE.md`, `docs/decisions/`

1. README remote-runner section: snapshot flow, provenance, cautions.
2. `CLAUDE.md` (tracked and installed copies): snapshot is the way to test
   uncommitted work; DUT evidence is valid when `dut_commit` equals the
   reported snapshot commit and `dut_clean` is true; pushing and WIP branches
   remain available but are no longer needed for this purpose.
3. ADR 0002 recording the decision.

Verification: `git diff --check`; wording reviewed by the owner.
Completion: documents consistent with behavior.

### Increment F — Security review of the new code

Dependencies: Increment D
Affected areas: `bin/remote-runner`

1. `security-review` skill and an independent adversarial pass on the snapshot
   builder, bundle transport, and worker action; regression tests first.

Verification: tests; findings recorded.
Completion: no unresolved Critical or High findings.

### Increment G — Live verification and install

Dependencies: Increments B, E, F
Affected areas: `~/.claude`, runner `ned`

1. Reviewed `./install.py --dry-run`, then the approved live install.
2. With the owner's approval, one real `remote-runner submit --snapshot` of a
   small throwaway repository to `ned`; confirm `status`, `log`, and `prune`.

Verification: `./install.py --check`; job status shows the snapshot
provenance.
Completion: completion criteria met.

## Verification

`python3 -I -m unittest discover -s tests`; `./install.py --check`;
`git diff --check`; permission probes; one real job on `ned`.

## Risks and sensitive actions

- **A snapshot executes working-tree code on a remote host**, including an
  uncommitted `.claude/remote-runner.toml`. `remote-runner submit` therefore
  prompts the owner.
- **A snapshot can include untracked secrets** that are not git-ignored. The
  scan refuses private-key and credential patterns; the runner is
  owner-configured, which limits exposure.
- **Permission changes** alter what prompts. They are reviewed as a dry-run
  before the live install, and the previous `settings.json` is backed up.
- **`CLAUDE.md` is the owner's private policy file**; edits are shown for
  review before install.
- Real network use is limited to one job on `ned` in Increment G.
- Commit and push only on explicit approval.

## Deferred work

- Incremental bundles and submodule support.
- Allowing `submit --snapshot` without a prompt for a fixed set of profiles.
- A downloadable artifacts command.

## Result

<!-- Complete after verification; archive per docs/plans/README.md. -->

### Increment A (2026-10-15): complete, committed as `b388ec5`

Scope reviewed: `bin/remote-runner`, `bin/claude-workflow`,
`skills/graphify-workflow/scripts/`, `hooks/review_agent_guard.py`, and
`skills/freecad-scripts/scripts/mesh_report.py` (`--json` target only). Each
component had two to four independent adversarial passes (`security-reviewer`
agent, scratch experiments); every fix has a failing-first regression test in
`tests/test_*_review.py` and `skills/graphify-workflow/tests/test_scripts_review.py`.
Full suite: 389 tests OK (5 skipped differential); Graphify suite: 52 OK.
Also verified against graphifyy 0.9.91 in a scratch venv.

Fixed: symlink and option-injection writes (`remove`, `commit`, graphify-out
state files), nested and embedded git directories, `core.worktree` redirects,
credential leaks in origin URLs, AI-attribution spellings, forged job records
crashing or hiding jobs in `remote-runner`, cancel without verified process
identity, log FIFO hang, guard bypasses (globs, `cd`, git pathspecs, repo
config that runs programs, `git grep`/`rg` pattern and glob overrides, URL
shorthand, cp/mv flags, session binding), Graphify freshness forgery and
unvalidated manifest, token, and chunk data. New guard modes `committer` and
`chunk` attached to `safe-committer` and `graphify-semantic`.

Accepted residuals: job-writable runner metadata (same user); security-mode
write confinement is advisory, not a sandbox; tracked or historical secrets are
readable via git objects; `implementer` has no guard mode (instruction-bound);
`remove --confirm` is not bound to the preview digest; Graphify manifest and
state are unsigned (same-trust forging possible); a missing `semantic_head` in
a legacy state file is still read as current; `git config --get remote.*.url`
is allowed in reviewer mode.

Not yet done: Increments B–G. Nothing from Increment A is installed to
`~/.claude`; install only after the reviewed dry-run in Increment G (or earlier
on request).

### Increment B (2026-10-15): complete, committed as `5f780e2`

`settings.json` and new `tests/test_permissions.py` (16 tests; full suite 405
OK, 5 skipped). `allow` gains read-only git (`ls-files`, `blame`, `describe`,
`remote -v`, `for-each-ref`, `worktree list`, `branch --list`), `git add`,
`git mv`, and `remote-runner remotes|recommend|status|log|artifacts`;
`claude-workflow commit` leaves `allow`. `ask` gains `claude-workflow
commit|amend-message|remove` and `remote-runner submit|cancel|prune` in the five
helper spellings, plus `git commit|push|tag|switch|stash`, branch deletion,
`gh`, `ssh`, `scp`, `rsync`, and package installs. `deny` gains `Read` of
`**/.env`, `**/.env.*`, `~/.ssh/**`, `~/.aws/**`, `~/.config/gh/**`,
`~/.codex/auth.json`, and `rmdir`, `unlink`, `shred`.

Deviation from the plan: precedence is deny > ask > allow, so an `ask` rule on
`git tag` or `git stash` would shadow an allow of `tag --list` or `stash list`.
Both are ask-only and `git for-each-ref` replaces `tag --list`; a test rejects
any allow rule shadowed by an ask or deny rule.

Not probed: the new wildcard forms cannot be exercised until the rules are
installed, because the live engine reads `~/.claude/settings.json`. The probe
moves to Increment G (harmless no-ops: `git push --dry-run`, `git commit
--dry-run`, `remote-runner prune`, `Read` of a scratch `.env`). Residual: rules
are literal prefixes, so spellings such as `git -C <dir> commit` or a relative
`python3 bin/claude-workflow commit` are not matched and fall to the
auto-mode classifier.

### Increment C (2026-10-15): complete, committed as `ddd568e`

`snapshot()` in `bin/remote-runner` and `tests/test_remote_runner_snapshot.py`
(27 tests; full suite 432 OK, 5 skipped). It builds a commit of the working
tree on `HEAD` inside a temporary bare repository that borrows the source
object store, so the source index, refs, stash, objects, and working tree are
unchanged (asserted). Files are read with `O_NOFOLLOW` per path component and
hashed with `--no-filters`; tracked files are compared by raw blob id because
`git ls-files -m` runs clean filters (found by a failing test). Hooks,
fsmonitor, and signing are disabled and ambient `GIT_*` variables are dropped.
Identity is fixed (`remote-runner <noreply>`). `project_config()` gained
`git_dir` so the contract is read from the snapshot.

Refusals, path only and never content: no commit, unresolved conflicts,
credential file names (`.env*` except templates, `id_*`, `.netrc`, `*.key`,
`*.p12`, `.aws/credentials`, and similar), private-key content under any name,
size over 64 MiB, over 5000 changed files, a symlinked parent directory, and a
non-regular tracked replacement. Only content that differs from `HEAD` is
scanned, because `HEAD` is already on origin.

Notes: FIFOs and untracked nested repositories are skipped, as git does;
submodule gitlinks keep their recorded commit; SHA-256 repositories are
refused. Whole tracked tree is read to compare blob ids (IO cost on very large
trees). Next: Increment D (bundle transport and worker action).

### Increment D (2026-10-15): complete, committed as `8632655`

`bin/remote-runner` and `tests/test_remote_runner_snapshot_submit.py` (16
tests; full suite 448 OK, 5 skipped). `submit --snapshot` (exclusive with
`--ref`) builds the snapshot, bundles it on top of `HEAD`, and sends one stream
over ssh: `python3 -I -c BOOTSTRAP`, then a length line, exactly that many bytes
of the worker script, then the bundle. The `submit-snapshot` worker action
validates object IDs, size (256 MiB limit), and SHA-256 before reading;
receives exactly the declared bytes and refuses a short stream, trailing data,
or digest mismatch; fetches the base from origin (so an unpushed base fails
with a push message and leaves no job directory); runs `git bundle verify` and
fetches only `refs/snapshot/head` with `transfer.fsckObjects`; requires the
fetched commit to equal the declared commit and to have exactly the declared
base as its only parent; then uses the existing worktree and `dut_commit` /
`dut_clean` checks on the snapshot commit. Records `snapshot`, `base_commit`,
and `snapshot_ref`; `status` reports `snapshot` and `base_commit`. Prune and
the failure path delete `refs/snapshots/<job>`; the bundle and worktree go with
the job directory. Plain `submit` is unchanged.

Notes: runner objects from a pruned snapshot remain until git's own gc;
the base must already be on origin (a bundle carries no base history).
Reviewed next in Increment F; E (docs/policy) comes first.

### Increment E (2026-10-15): complete, wording approved by the owner

`README.md` (snapshot section, revised submission intro), `CLAUDE.md` tracked
copy (default job wording; snapshot provenance rule; snapshot is the way to
test uncommitted work; WIP branch retained as an owner-requested alternative),
and ADR 0002 with its index row. `~/.claude/CLAUDE.md` is **not** changed: the
owner reviews the tracked wording first, and the installed copy is updated with
the Increment G install. `test_install.py` passes (75 OK, 5 skipped).

### Increment F (2026-10-15): complete

Independent adversarial `security-reviewer` pass (scratch experiments with
hostile git config, filters, hooks, path names, crafted bundles, a directory
swap race, BOOTSTRAP lengths, prune with rewritten records). No Critical or
High findings. Repository-configured programs never ran; hostile trees
(`.git` variants, `.gitmodules`, case collisions) were rejected by the worker's
fsck-enabled fetch or the clean-checkout check; no out-of-tree read occurred in
20000 race iterations.

Fixed with regression tests (`tests/test_remote_runner_snapshot*.py`, 72 remote
runner tests OK): prune leaked `refs/snapshots/<job>` when a job rewrote its
`cache` field (now removed from every cache by directory name); the bundle was
retained (deleted after the verified fetch); SIGTERM left temporary snapshot
copies (handler unwinds the context managers); `--source-ref` was unvalidated
and not `--`-separated, and a plain-submit `--commit` was unvalidated (both now
validated); a swap race gave a traceback (now a clean refusal).

Accepted: the secret scan is best-effort (documented in the README); a hardlink
to an outside plain file is included; the rest of the trust model matches
ADR 0002. Not tested: a Linux runner with git older than 2.24 (fsck on fetch is
the protection that was exercised, on macOS git only; Increment G runs a real
job on `ned`).

### Increment G (2026-10-15): live install done; probes inconclusive; ned job pending

`./install.py` ran after the reviewed dry-run (backup
`~/.claude/backups/claude-global-config-20261015T194951Z`); `./install.py
--check` reports a match. Probes in the installing session were inconclusive:
`Read` of a scratch `.env` (absolute path) returned its content and `git push
--dry-run` ran without a prompt, which indicates this session had not reloaded
`settings.json` (not proof the rules are wrong). Repeat the probes in a fresh
session. Not yet done: one real snapshot job on `ned` (needs the owner's go-ahead).
