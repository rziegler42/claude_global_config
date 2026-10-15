# 0001: Codex plan review runs read-only with a prompt-only read boundary

Status: Accepted
Date: 2026-10-15

## Context

The owner reviews implementation plans by copying them between Claude Code and
the ChatGPT/Codex application. `ask-codex` runs that review from Claude Code
using the owner's ChatGPT login through `codex exec`, so no API key or
per-token billing is involved.

Codex needs to read the repository to verify a plan's claims (for example that
a file uses argparse). The `codex exec -s read-only` sandbox prevents writes,
but verification in Increment A of the plan showed it does **not** prevent
reads outside the working directory: Codex could read both a file inside and a
file outside the directory it was started in. Anything the owner's account can
read, including ignored files such as `.env`, `~/.ssh`, and the helper's own
`.seal-key`, is reachable if Codex decides to look.

## Decision

Run Codex in the live repository, read-only, with these controls:

- The prompt instructs Codex to stay inside the repository and not to read
  secrets, credentials, `.env` files, or ignored files. This is the only read
  boundary, and it is a prompt, not an enforced sandbox.
- Codex is started with a minimal environment (`PATH`, `HOME`, `CODEX_HOME`,
  `LANG`, `LC_ALL`, `TERM`, `TMPDIR`), `--ephemeral`, `--ignore-user-config`
  (so none of the owner's MCP servers or plugins load), and stdin closed.
- `codex` and `git` are resolved only from absolute `PATH` entries outside the
  repository.
- Claude is the only writer; Codex output is untrusted data, bounded in size,
  and validated against a strict schema.

The owner accepted this explicitly, knowing the boundary is prompt-only.

## Alternatives considered

- **Plan only.** Copy just the plan into a scratch directory. Safest, but the
  review cannot check claims against the code, so it is much shallower.
- **Snapshot of non-ignored files plus a scrubbed environment.** Excludes
  ignored files such as `.env`, but still allows absolute-path reads outside
  the snapshot, and loses uncommitted state fidelity.
- **OS-level isolation** (container or `sandbox-exec`). Would enforce the
  boundary, but differs between macOS and WSL, may break Codex's own needs, and
  was judged out of scope.

## Consequences

- Everything Codex reads is sent to OpenAI. No secrets belong in a plan, and the
  skill reminds Claude of this.
- A hostile repository can influence the review through its content; the
  helper's own checks (path containment, strict output, caps, tamper-evident
  state) limit what a review can do, not what Codex can read.
- If real isolation becomes necessary, the runner is the single place to add
  it (a container or snapshot), without changing the loop, state, or skill.

## Verification

- Increment A (2026-10-15): a read-only run read a marker file outside its
  working directory.
- `tests/test_ask_codex.py`: exact argument list, scrubbed environment, closed
  stdin, executable resolution, and output validation, using a fake `codex`.
- Increment G: a real end-to-end loop and a model calibration.

## Related files and decisions

- `docs/specs/second-opinion-plan-review.md` (Security and privacy, Accepted
  residual risks)
- `bin/ask-codex`, `ask-codex/kinds/plan-review/prompt.md`
