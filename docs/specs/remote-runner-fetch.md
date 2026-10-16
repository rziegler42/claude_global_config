# Remote-runner fetch: retrieve job output files

Status: Accepted (implemented; security-reviewed)
Date: 2026-10-16

## Purpose

A remote job (for example `connect4` training on `ned`) can produce untracked
files such as model weights. `remote-runner artifacts` lists them, but nothing
brings them back, and an arbitrary `scp`/`rsync` is outside policy. This
specification defines `remote-runner fetch`, a bounded, owner-approved way to
copy named regular files from a finished job's worktree to the local machine.

## Scope (version 1)

- A new controller subcommand `fetch` and a matching worker operation, carried
  over the existing SSH worker channel (`invoke_worker`).
- Retrieval of explicitly named regular files from `<job>/worktree/`.
- Local placement at the same relative path under the repository root, with
  `--dest` and `--as` overrides.
- A `settings.json` permission entry, tests, an ADR, and documentation.

## Non-goals

- Directory, glob, or recursive fetch.
- Resume, compression, or incremental sync.
- Fetching from a pruned job or from outside `worktree/` (logs, metadata).
- Pushing local files to a runner.
- Changing job execution, provenance, or `artifacts` listing behavior.

## Interface

```text
remote-runner fetch <job> <path>... [--dest DIR] [--as NAME] [--force]
```

- `<job>` is a job ID; the remote is derived from it as for `status`.
- `<path>` is relative to the job's `worktree/`. At least one, at most 16.
- `--dest DIR`: local directory that replaces the repository root as the base.
  It must already exist. The file lands at `DIR/<path>`.
- `--as NAME`: replaces the basename of the single fetched file. Valid only
  with exactly one `<path>`. `NAME` is a plain filename: non-empty, no `/`,
  no NUL, not `.` or `..`, not starting with `-`.
- `--force`: allow overwriting an existing local file, a local path that git
  tracks, and a path with a dot-prefixed component (for example `.claude`,
  `.ssh`, `.envrc`). Git metadata is never allowed, with or without it.

Default placement: `<repo root>/<path>`. Examples:

| Command | Local file |
|---|---|
| `fetch J checkpoints/latest.pt` | `<repo>/checkpoints/latest.pt` |
| `fetch J checkpoints/latest.pt --as model-v3.pt` | `<repo>/checkpoints/model-v3.pt` |
| `fetch J checkpoints/latest.pt --dest weights` | `weights/checkpoints/latest.pt` |
| `fetch J checkpoints/latest.pt --dest weights --as m.pt` | `weights/checkpoints/m.pt` |

Output is JSON: the job, its `dut_commit` and `integrity` (as in `status`),
and per file `remote_path`, `local_path`, `bytes`, `sha256`. All job-derived
fields are marked `untrusted_job_data`.

## Worker behavior (runner)

- Reject a `<path>` that is absolute, contains `..`, an empty component, NUL,
  or starts with `-`.
- Refuse unless the job state is `PASSED`, `FAILED`, or `FINISHED`, so a
  half-written file is never fetched. The state is recomputed by the worker
  (`refresh_state`), not read from job-writable metadata alone.
- Open each file relative to a directory fd for `worktree/` with `O_NOFOLLOW`
  at every component; a symlink anywhere in the path is refused. Only a
  regular file is accepted; its size is taken from `fstat` of the open fd.
- Limits: 16 files, 512 MiB total, enforced before streaming and while reading
  (a file that grows is truncated-and-failed, not sent).
- Stream a length-framed protocol (name, size, SHA-256, bytes, per file) on
  stdout. No archive format is used, so the controller never interprets
  member names or metadata chosen by the job.

## Controller behavior (local)

- Resolve the base (repo root or `--dest`) and require the final path to stay
  inside it with no symlink in any existing component.
- Refuse to overwrite an existing file, and refuse a path tracked by git
  (in the working repository or the destination's own, compared with case and
  Unicode-normalisation folding, and including a tracked directory of the same
  name), unless `--force`. Refuse any target inside git metadata by name or by
  file identity of the repository's git directories, always. Directories
  missing under the base are created.
- Paths that differ only by case or Unicode normalisation are one name.
- The transfer is bounded: a non-interactive SSH connection with keep-alive, an
  idle limit of 120 s, an overall budget of that allowance plus the declared
  size at 256 KiB/s, and runner stderr kept to 4 KiB. SIGTERM, SIGHUP, SIGQUIT,
  SIGUSR1/2, and SIGALRM remove staged files; SIGKILL cannot.
- Write to a temporary file in the destination directory, verify byte count
  and SHA-256 against the frame, then atomically rename. On any failure
  nothing is left at the destination and temporary files are removed.
- Validate every frame field (name equals a requested path, size within
  limits) and refuse unexpected or extra frames.
- File mode is set to `0644`; the remote mode is ignored.
- Validate all targets before the first write, so a refusal leaves no partial
  set when several files are fetched.

## Permissions

`fetch` writes remote-controlled content to the local disk, so every spelling
that `submit` uses (`remote-runner`, `~/.claude/bin/…`, `~/.local/bin/…`,
`python3 [-B] ~/.claude/bin/…`) is added to `permissions.ask` in
`settings.json`. `artifacts` stays allow-listed as the discovery step.

## Acceptance criteria

1. `fetch` of one file from a finished job writes it at the default path with
   the correct bytes and a reported SHA-256.
2. `--dest`, `--as`, and their combination place the file per the table above.
3. `--as` with several paths, or with a name containing a separator, `..`,
   NUL, a leading `-`, or empty, is refused before any SSH call.
4. Refused, with no local change: absolute or traversing paths, a symlink
   component, a non-regular file, a RUNNING/STARTING/CANCELLED/UNKNOWN job,
   more than 16 files, over 512 MiB, an existing target without `--force`, a
   git-tracked target without `--force`, a `--dest` that does not exist, and
   a target that escapes the base through a symlink.
5. A checksum or length mismatch, extra frame, or truncated stream leaves no
   file and no temporary file at the destination.
6. Output reports `dut_commit` and `integrity` for the job.
7. `settings.json` lists `fetch` under `ask` for all spellings, and the
   existing permission tests cover it.
8. Tests run against a local fake worker without SSH, in the style of
   `tests/test_remote_runner_snapshot_submit.py`, and a security review
   (adversarial path, symlink, and frame probes) finds no unresolved issue.
9. A live fetch of a `connect4` checkpoint from `ned` succeeds, and a local
   `sha256sum` of the result equals the SHA-256 the command reported.

## Accepted limits

- A multi-file fetch that fails while placing reports what was already placed
  and does not roll it back.
- A job record that falsely claims to be finished can expose that job's own
  half-written file.
- Non-dot, code-adjacent names are the owner's decision at the permission
  prompt; fetched content is untrusted.

## Assumptions and constraints

- The runner needs only Python 3 and the streamed worker script, as today.
- The job and its worktree are untrusted data; metadata is job-writable.
- The runner is owner-configured; confidentiality of fetched files in transit
  rests on the existing SSH channel.
- Portable global policy changes are mirrored to both this repository and
  `~/.claude`.

## Related

- `bin/remote-runner` (`invoke_worker`, `worker`, `artifacts`)
- `docs/decisions/0002-snapshot-bundle-submission.md`
- ADR 0003 (to be written with the plan): fetch over the worker channel using
  a framed protocol rather than tar or scp.
