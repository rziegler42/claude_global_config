# 0002: Second opinion: bounded Codex plan review

Status: Completed
Created: 2026-10-15
Completed: 2026-10-15

## Outcome

`ask-codex` and the `second-opinion` skill let Claude Code run a bounded,
read-only Codex review loop on `docs/plans/next.md` using the owner's ChatGPT
subscription. Claude is the only writer, the helper owns the round counter and
the bound, every owner-only action prompts, and review state is sealed against
accidental edits. Governing documents: `docs/specs/second-opinion-plan-review.md`
and ADR 0001.

## Scope

- `bin/ask-codex` (Python 3.9, standard library only): `init`, `status`,
  `models`, `review-plan`, `decide`, `extend`, `reset`, `archive`, `prune`.
- `ask-codex/config.json` and the `plan-review` kind (prompt, strict schema).
- `skills/second-opinion/SKILL.md`.
- Manifest entries, the `ask-codex` link in `install.py`, and `settings.json`
  `allow`/`ask` rules.
- Tests with a fake `codex`, two security reviews, one real end-to-end run, and
  a model calibration.

## Non-goals

- Automatic triggers, other review kinds, or Codex writing to any file.
- Changes to `claude_project_template`.
- Pre-commit enforcement, an MCP server, or API-key based access.

## Assumptions

- Python 3.9+ standard library only; macOS primary, Linux and WSL secondary.
- Codex CLI 0.162.1 signed in with the ChatGPT login.
- Real Codex calls consume the owner's allowance and were limited to
  Increments A and G.

## Completion criteria

All met; evidence is under Verification.

## Constraints

- Commit and push only on explicit owner approval.

## Increments

### Increment A — Verify the Codex behaviors the design relies on

Dependencies: Spec approved
Affected areas: scratch only; spec Verification section

1. Verify `--ignore-user-config`, `--output-schema` with `-o`, token usage
   reporting, and failure modes.

Completion: behaviors confirmed and recorded in the spec. Met.

### Increment B — Helper core with a fake Codex

Dependencies: Increment A
Affected areas: `bin/ask-codex`, `ask-codex/`, `tests/`

1. Config, kind registry, state, ledger, lock, plan containment, `decide`,
   `status`, with tests first.

Completion: 38 tests. Met.

### Increment C — Runner, policy, and failure handling

Dependencies: Increment B
Affected areas: `bin/ask-codex`, `tests/`

1. `review-plan`, `models`, catalogue validation, failure classification,
   convergence, re-raise, and effort escalation.

Completion: every stop condition exercised by a test. Met.

### Increment D — Lifecycle commands

Dependencies: Increment C
Affected areas: `bin/ask-codex`, `tests/`

1. `extend`, `reset`, `archive`, `prune` and their safety rules.

Completion: spec criterion 1a met. Met.

### Increment E — Skill, installer, and settings

Dependencies: Increment D
Affected areas: `skills/second-opinion/`, `config-manifest.txt`, `install.py`,
`settings.json`, tests

1. Skill, manifest, helper link, `allow` and `ask` rules, wiring tests,
   reviewed dry-run, approved live install.

Completion: `./install.py --check` clean after the install. Met.

### Increment F — Security review

Dependencies: Increment E
Affected areas: `bin/ask-codex`, tests

1. `security-review` pass, then two independent adversarial reviews, with a
   failing regression test before each fix.

Completion: no unresolved Critical or High findings. Met.

### Increment G — Real end-to-end run and calibration

Dependencies: Increment F
Affected areas: scratch repositories, spec

1. Real loop on a throwaway plan; model calibration on one archived plan.

Completion: default model pinned with evidence. Met.

### Increment H — Documentation and close-out

Dependencies: Increment G
Affected areas: `README.md`, `docs/decisions/`, `docs/specs/`, `docs/plans/`

1. README usage section, ADR 0001, spec accepted, plan archived.

Completion: met.

## Verification

- `python3 -I -m unittest discover -s tests`: 279 tests passing (5 skipped
  differential tests, which need the removed `install.sh`).
- Real end-to-end run on a throwaway plan: round 1 found all three planted
  flaws (a false claim about argparse, a destructive out-of-repo deletion as a
  blocker, an unverifiable completion criterion); round 2 converged. About 110k
  tokens for two rounds on a 25-line plan.
- Calibration (one archived plan, one round each, `high`): `gpt-6.1-sol` and
  `gpt-6-astra` returned the same single real major finding, with no false
  blockers or majors; sol 176k input tokens, astra 191k and 59 s. The default
  model stays `gpt-6.1-sol`.
- First use on a real plan (this one, round 1): one major finding about
  install timing, recorded under Result.
- Security: two independent adversarial reviews, no Critical or High findings;
  all code-level findings fixed with regression tests.

## Deferred work

- Automatic triggers, additional review kinds (diff, free-form question), and
  the neutral wording in `claude_project_template`.
- Preserving full review history outside `.debug/`.
- A `/dev/tty` confirmation for `extend`, `reset`, and `prune --confirm`, if the
  owner wants a boundary stronger than permission rules.
- A freshness mark outside the repository against state rollback.

## Result

Implemented in `claude_global_config` (not yet committed at archive time).
Closed with `ask-codex archive` on 2026-10-15.

### Codex review of this plan (summary printed by `ask-codex archive`)

- Plan: docs/plans/next.md
- Rounds used: 1 of 3; round 1 used `gpt-6.1-sol` at `high` with 185,061 input
  and 1,708 output tokens.
- Outcome: not converged after one round; one major finding, applied, and no
  second round was run.
- Decisions: 1 applied, 0 rejected.

Finding R1-F1 (major): the live install happened in Increment E, before the
security fixes in F, so the real run in G might have exercised a stale
installed helper, and the plan did not say which executable G tested. What
actually happened: a second reviewed and approved live install followed the
fixes (backup `claude-global-config-20261015T174535Z`), `./install.py --check`
was clean, and `cmp bin/ask-codex ~/.claude/bin/ask-codex` showed the installed
helper identical to the repository helper before Increment G ran the real loop.

### Deviations from the approved plan

- **`init` subcommand** added so state handling was testable before the runner.
- **Exit codes:** 0 command succeeded (including a round with findings), 1 a
  stop condition fired, 2 usage or fatal error.
- **State directories** are `<date>-plan-review` with `-2`, `-3` suffixes.
- **`archive` is owner-gated** (permission prompt) after the first review showed
  it could be used to start a fresh review.
- **Plan identity:** an open review belongs to its plan file; archive records
  the plan identity at close.
- **State integrity:** HMAC seal plus per-round digests (tamper-evidence only).
- **Executable resolution** from absolute `PATH` entries outside the repository.
- **Test-integrity bug found and fixed:** a helper named `fail()` in the test
  case base class shadowed `unittest.TestCase.fail()` and made several
  assertions unable to fail; renamed, and all tests re-run honestly.
- **Documentation correction:** both models in the calibration found a false
  statement in the README and in plan 0001 about removed settings keys; fixed.
- **Accepted residual risks** are listed in the specification.
