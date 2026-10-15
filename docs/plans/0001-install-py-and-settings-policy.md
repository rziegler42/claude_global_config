# 0001: Replace install.sh with a policy-aware install.py

Status: Completed
Created: 2026-10-15
Completed: 2026-10-15

## Outcome

`install.py` (Python 3.9, standard library only) replaces `install.sh` with the
same CLI and safety behaviour. It manages `settings.json` by policy so
intentional local preferences and extra plugins are no longer reported as
drift, verifies required plugins are installed, checks and tightens file
modes, and applies the hardening found in two security reviews.

## Scope

- `install.py` reproducing the documented `install.sh` behaviour.
- Policy-aware `settings.json` handling via `settings-policy.txt`.
- Tests, `README.md` updates, removal of `install.sh`.

## Non-goals

- A `--remove` flag, pruning `backups/`, new manifest entries.
- Installing, updating, or removing plugins or other external dependencies.
- The Codex `second-opinion` helper and skill.
- Mirroring local-only state such as `model` or `modelSettings` into the repo.

## Assumptions

- The CLI stays: `--dry-run`, `--check`, `--no-link-bin`, `-h`, with
  `CLAUDE_CONFIG_DIR` and `LOCAL_BIN_DIR`; exit 0, 1 (check drift), 2.
- The manifest is an allowlist; nothing is ever deleted.
- Policy categories: `preference` (seeded only when absent, never reported),
  `open` (repository entries enforced, extras allowed), and strict for
  everything else.

## Completion criteria

- Characterization tests pass against both installers and a differential run
  matches trees and output. Met.
- Policy tests pass for each category, idempotency, atomic write, malformed
  JSON, and plugin presence. Met.
- `./install.py --check` on the real `~/.claude` reports no drift while
  preserving `model`, `modelSettings`, and extra plugins. Met.
- `install.sh` removed and `README.md` references `install.py`. Met.
- `security-review` completed on the merge and path-handling code. Met.

## Constraints

- No dependency additions; commit only on approval; never push without it.

## Increments

### Increment A — plan lifecycle and characterization tests

Dependencies: None
Affected areas: `docs/plans/`, `tests/test_install.py`

1. Establish the plan lifecycle and pin `install.sh` behaviour with
   installer-agnostic tests.

Completion: 16 tests pass against `install.sh`. Met.

### Increment B — port to `install.py`

Dependencies: Increment A
Affected areas: `install.py`, `tests/`

1. Implement parity behaviour; run the same tests plus a differential test.

Completion: tests and differential run pass. Met.

### Increment C — settings policy

Dependencies: Increment B
Affected areas: `install.py`, `settings-policy.txt`, `tests/`

1. Tests first, then the merge, `--check` reporting, seeding, plugin presence.
2. `security-review`, then an independent adversarial review of the fixes.

Completion: policy tests pass; review findings fixed. Met.

### Increment D — switch over

Dependencies: Increment C
Affected areas: `README.md`, `install.sh` (removed)

1. Update `README.md`, remove `install.sh` after preview, verify against the
   real `~/.claude`.

Completion: criteria above met on the real configuration. Met; the live
install was a no-op because the dry-run showed nothing to change.

## Verification

- `python3 -I -m unittest discover -s tests`: 130 tests passing (5
  differential tests skip once `install.sh` is gone).
- `./install.py --check` on the real `~/.claude`: matches; `--dry-run` shows
  only the already-correct helper links.
- Permission audit of the tracked repo and `~/.claude`: no problems.
- `git diff --check` clean.

## Deferred work

- A key removed from the repository stays in the installed file; no
  `--remove` or pruning of `backups/`.
- The Codex `second-opinion` helper, skill, and trigger design.
- A neutral shared workflow helper in place of `claude-workflow`.

## Result

Implemented in one commit on `main` (not pushed). Deviations from the approved
plan, each recorded here:

- **File-mode rules added** at the owner's request: `settings.json` has no
  group or other access (fresh installs are `0600`), files whose repository
  source is executable keep the owner execute bit, no managed file is group-
  or world-writable, and backup directories are `0700`. Modes are only ever
  tightened.
- **Security hardening beyond the plan**, from two reviews: canonical and
  case-insensitive manifest path checks, duplicate rejection, symlinked-source
  and out-of-repository source refusal, destination escape and
  `settings.json` aliasing refusal, a protected-key list that policy cannot
  relax, duplicate policy lines rejected, terminal-control escaping, NaN and
  deep-nesting rejection, type-aware JSON comparison, a pre-write recheck of
  `settings.json`, unique private backup directories, and clean exit 2 on
  invalid input or I/O failure.
- **Synced plugins** (`design@synced`, `pdf-viewer@synced`) were removed from
  the repository's `settings.json` as unmanaged local state.
- **`install.sh` was removed**, with no compatibility wrapper.
- A manifest source missing mid-list is now rejected before anything is
  written; `install.sh` failed midway after installing earlier entries.
