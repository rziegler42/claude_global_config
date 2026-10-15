# 0002: Test uncommitted work by submitting a snapshot bundle

Status: Accepted
Date: 2026-10-15

## Context

`remote-runner` ran only a committed revision reachable from `origin`.
Testing uncommitted work therefore needed a temporary pushed WIP branch: a
commit, a push, and later cleanup, each an outward action the owner had to
approve. That friction pushed long checks to run locally or not at all.

## Decision

Add `remote-runner submit --snapshot`. The controller builds a commit of the
working tree on top of `HEAD` in a temporary repository that borrows the source
object store, bundles it, and streams the bundle over the existing SSH channel
after a length-prefixed copy of the worker script. The worker verifies size and
SHA-256, fetches the base from `origin`, verifies the bundle, fetches only the
snapshot ref with fsck enabled, requires the commit to sit directly on the
declared base, and runs the job from a worktree of the snapshot commit.

- The source repository is never changed: no commit, ref, index, stash, or
  working-tree write. Files are read without following symlinks and without
  clean filters; no hook or repository-configured program runs.
- The snapshot uses the fixed identity `remote-runner <noreply>`.
- Credential file names, private-key content, and oversize snapshots are
  refused, naming the path only.
- Provenance is kept: `dut_commit` equals the snapshot commit, `dut_clean` is
  true, and `base_commit` names the local `HEAD`.
- `submit` stays an owner-prompted action in `settings.json` because a
  snapshot executes working-tree code, including an uncommitted contract, on
  the runner.

## Alternatives considered

- **WIP branch push.** Keeps the pushed record and needs no new code, but
  repeats the commit, push, and cleanup approvals; still available.
- **rsync or working-directory sync.** Breaks DUT provenance and copies
  ignored files; rejected by policy.
- **Bundle with full history.** Would allow an unpushed `HEAD`, at the cost of
  size and a larger trust surface; deferred.

## Consequences

- Uncommitted work can be tested remotely with one approved action.
- The base commit must be on `origin`.
- An untracked secret with an unrecognized name is sent to the runner; the
  runner is owner-configured, which limits exposure.
- Runner objects from pruned snapshots persist until Git garbage collection.

## Verification

`tests/test_remote_runner_snapshot.py` and
`tests/test_remote_runner_snapshot_submit.py` (builder, source immutability,
refusals, bundle transport, provenance, prune). A security review is Increment
F of `docs/plans/next.md`; a live job on `ned` is Increment G.

## Related

- `docs/plans/next.md`
- `bin/remote-runner`
