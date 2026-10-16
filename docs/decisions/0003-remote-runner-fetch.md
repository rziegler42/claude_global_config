# 0003: Retrieve job output with a framed fetch over the worker channel

Status: Accepted
Date: 2026-10-16

## Context

A remote job can produce untracked output, such as model weights from a
`connect4` training run. `remote-runner artifacts` only lists files, and the
policy forbids arbitrary `scp`, `rsync`, or `ssh` commands, so there was no
sanctioned way to bring a result back. The job tree and its metadata are
written by the job and are untrusted; the runner stream is untrusted to the
controller; fetched bytes land in the owner's repository.

## Decision

Add `remote-runner fetch <job> <path>... [--dest DIR] [--as NAME] [--force]`,
carried over the existing SSH worker channel.

- **Framed stream, not an archive.** The worker sends a header (job view and
  file sizes) followed, per file, by its bytes and a SHA-256 line. The
  controller never interprets member names or modes chosen by the job.
- **Worker side.** Paths are validated, then opened relative to directory file
  descriptors with `O_NOFOLLOW`; only regular files are sent, within 16 files
  and 512 MiB. A job must be `PASSED`, `FAILED`, or `FINISHED`, and a record
  claiming that while its process is alive is refused.
- **Controller side.** Files are staged beside the destination base, verified
  for length and digest, and placed only after the whole stream and the
  worker's exit succeed. Placement uses directory descriptors with
  `O_NOFOLLOW`, a no-clobber `link` (or `rename` with `--force`), and mode
  `0644`.
- **Refusals.** Git metadata is never a target, by name and by file identity.
  A dot-prefixed path component, an existing file, and a git-tracked file
  (in the working repository or the destination's own, compared with case and
  Unicode folding) need `--force`. Paths that collide after folding are one
  name.
- **Bounds.** The SSH connection is non-interactive and keep-alive bounded; a
  watchdog ends a transfer that is idle for 120 s or exceeds an overall budget
  of that allowance plus the size at 256 KiB/s; runner stderr is kept to 4 KiB;
  termination signals unwind the staging cleanup.
- **Permission.** `fetch` is an owner-prompted (`ask`) action in all five
  command spellings. `artifacts` stays allowed as the discovery step.
- `--dest` sets the base directory (default: the repository root) and `--as`
  renames the basename of a single fetched file.

## Alternatives considered

- **Controller-side `scp` or `rsync`.** Less code, but the remote path and
  symlink rules would be left to the remote filesystem and it adds arbitrary
  transfer surface. Rejected.
- **`tar` over the channel.** Needs a safe extractor for attacker-chosen
  member names and modes. Rejected for the framed stream.
- **A job that pushes or commits its output.** Contradicts keeping weights out
  of git and pushes data outward. Rejected.
- **A denylist of sensitive names.** Review showed it can never be complete;
  replaced by the dot-prefix rule plus the owner prompt, which shows the path.

## Consequences

- Untracked results can be retrieved with one approved action and a verified
  digest, without raw transfer permissions.
- Fetched content is untrusted. The digest proves the transfer, not the job's
  trustworthiness.
- Non-dot, code-adjacent names (for example `conftest.py` or a `Makefile`) are
  not blocked; the owner decides at the prompt.
- A multi-file fetch that fails during placement reports the files already
  placed and does not roll them back. `SIGKILL` can leave a staged
  `.rr-fetch-*.tmp` file in the destination base.
- A job record that lies about being finished can expose a half-written file of
  that job's own making.
- Behavior was reviewed on macOS (case- and normalisation-insensitive); other
  filesystems rely on the same folding being conservative.

## Verification

`tests/test_remote_runner_fetch.py` (validation, placement, transport through a
shim `ssh`, hostile streams, and regression tests for three independent security
review passes). The review record is in
`docs/plans/0004-remote-runner-fetch.md`.

## Related

- `docs/specs/remote-runner-fetch.md`
- `docs/decisions/0002-snapshot-bundle-submission.md`
- `bin/remote-runner`
