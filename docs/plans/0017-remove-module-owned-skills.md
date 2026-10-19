# 0017: Remove the module-owned skills from the global configuration and write the marker file

Status: Completed
Created: 2026-10-19
Completed: 2026-10-19

## Goal

Finish template roadmap candidate 10 (`claude_project_template/docs/roadmaps/module-harness-files.md`)
in this repository. After the plan, the `second-opinion` and `knowledge-base` skills exist only in
their template modules (`codex` and the knowledge-base starter), and `python3 install.py` writes the
marker file `~/.claude/global-config.json` that the template installer reads to report that the
global configuration is present.

## Scope

- Delete `skills/second-opinion/` and `skills/knowledge-base/` with their `config-manifest.txt`
  lines (both skills' files).
- Marker: add a tracked `global-config.json` containing exactly `{"schema": 1}` (the format fixed by
  the template's `docs/specs/module-harness-files.md`: a regular file, at most 4 KiB, a JSON object
  whose `schema` is the integer 1) and list it in `config-manifest.txt`, so `install.py` mirrors it
  like any other file. Owner decision: the marker is written by the mirror, not by a separate step.
- Tests:
  - Delete `tests/test_knowledge_base_skill_wiring.py` (it pins only the removed skill; the starter
    carries its own tests).
  - In `tests/test_second_opinion_wiring.py`, keep the helper, installer and permission checks, drop
    the `Skill` class and the skill files from the manifest check, and rename the file's description
    accordingly. `ask-codex`, its spec checks and the permission rules are unchanged.
  - Add a test that the marker is tracked, listed once in the manifest, valid JSON with integer
    `schema` 1, and under 4 KiB.
- Cross-references: remove the two skills from `README.md` and rewrite its `second-opinion` and
  `ask-codex` mentions to say the skill ships in the template's `codex` module; fix
  `skills/knowledge-base-authoring/SKILL.md` line 11, which tells the reader to use the
  `knowledge-base` skill, to say it is installed with a registered store through the template (the
  exact command is copied from the starter's README when the edit is made, not from memory).
- Records: a dated note on ADR 0008 (body unchanged) and on `docs/specs/knowledge-base-skills.md`
  that the consuming skill now ships with the starter; add the pointer from
  `docs/roadmaps/knowledge-base-skills.md` to the template roadmap and mark its candidate 2 skill as
  moved. No other roadmap candidate changes.

## Non-goals

- `knowledge-base-authoring`, `verilog-verilator-sim`, `security-review`, `architecture-decisions`, the
  generic agents, `ask-codex`, `remote-runner`, `claude-workflow`, hooks, settings and the approver
  rules all stay (template ADR 0004, decision 7).
- No change to the template or the starter.
- `hooks/codex_approver.py`'s `REVIEWER_FACING_PATHS` entry `skills/second-opinion/*` stays for now
  (see Deferred work).
- Deleting the `~/.claude` copies, which only the owner can do.

## Assumptions and constraints

- The conversions have landed (verified): `claude_project_template/modules/codex/harness/claude/skills/second-opinion`
  is byte-identical to `skills/second-opinion` here, and the starter ships
  `claude_knowledge_base/kit/files/template-module/harness/claude/skills/knowledge-base/SKILL.md`
  (a revised version: it requires owner confirmation of every store root). Template roadmap candidates
  3 to 9 are done.
- Marker contract, verified at template revision `9b0decb` (`docs/specs/module-harness-files.md`,
  "The harness table" and "Declarations", and the template README): a valid JSON object whose `schema`
  is the integer 1. Plan 0016's phrase "`global_config: true`" names the module's `module.json`
  declaration that makes the installer look for the marker, not the marker's content; the two are
  consistent. The template reads the marker from `~/.claude/global-config.json`, size-limited;
  it changes only what the installer reports and anyone with the owner's account can forge it
  (template spec). The mirror writes the same bytes everywhere, so the file carries no machine state.
- ADR 0008 and the knowledge-base spec are accepted and approved. Notes are dated additions; their
  bodies are not rewritten. This plan's approval covers those notes.
- Removing the skill removes it from every repository that did not install the module. A project
  with no `.claude/skills/second-opinion` after this loses `/second-opinion` until the owner runs
  `install.py --add codex --harness claude` there; the template roadmap found no existing project
  needing migration.

## Discovery and impact evidence

Graphify: skipped — the graph is missing, and a grep of the working tree for `second-opinion` and
`skills/knowledge-base` enumerates the affected files: the skills, `config-manifest.txt`, the two
wiring tests, `README.md`, `skills/knowledge-base-authoring/SKILL.md`, the ADR 0008, the
knowledge-base spec and roadmap, and records that stay unchanged (archived plans, ADRs 0001 and 0007,
the second-opinion specs, approver rule files and `bin/ask-codex` text). Template side read to
confirm the conversions and the marker format.

## Completion criteria

- Neither skill directory exists in the repository, and a fresh-destination `python3 install.py`
  (into a scratch directory, as `tests/test_install.py` does) creates neither. The existing
  `~/.claude` copies are outside the plan's control: the installer never deletes, so they remain until
  the owner removes them in a separate step, which the plan reports but does not require.
- `~/.claude/global-config.json` exists after `python3 install.py`, and the sibling template checkout's
  installer reports `global configuration: present` for it, with the three recorded outputs of
  Increment B, step 3.
- `python3 -B -m unittest discover -s tests` passes; `python3 install.py --check` reports a match.
- `grep -rIl --exclude-dir=.git --exclude-dir=.debug --exclude-dir=__pycache__ 'skills/second-opinion\|skills/knowledge-base/'`
  lists only archived plans, the notes in ADR 0008 and the spec, the roadmap, `ask-codex` and approver
  text kept for the deferred item, and this plan once archived.

## Increments

### Increment A — Remove the two skills and their tests

Dependencies: None
Affected areas: `skills/second-opinion/`, `skills/knowledge-base/`, `config-manifest.txt`,
`tests/test_second_opinion_wiring.py`, `tests/test_knowledge_base_skill_wiring.py`

1. Preview with `claude-workflow remove skills/second-opinion skills/knowledge-base --recursive`, then
   rerun the identical command with `--confirm`.
2. Remove their manifest lines; delete the knowledge-base wiring test; trim the second-opinion test as
   scoped.
3. Run the full suite.

Completion: the skills are gone, the suite passes, and the remaining second-opinion test still pins
the helper, installer link and permission rules.

### Increment B — Write the marker

Dependencies: A
Affected areas: `global-config.json`, `config-manifest.txt`, a new marker test

1. Add the file and its manifest line; add the marker test.
2. Run `python3 install.py` and confirm the file appears in `~/.claude`.
3. Prerequisite: the sibling checkout `../claude_project_template` at revision `9b0decb` (confirm
   with `git rev-parse --short HEAD`; if it has moved, record the new revision and re-check the marker
   contract against its spec first). Run its
   `install.py` as a new-project `--dry-run` with `--with graphify --harness claude` (the only
   module that declares `global_config`), into a scratch target, three times: with
   `--global-config` naming an empty scratch directory (expect `global configuration: missing`),
   with `--global-config` naming a scratch directory holding a copy of the marker (expect
   `present`), and with neither option, which reads the real `~/.claude/global-config.json`
   written in step 2 (expect `present`). The exact new-project flags are taken from that
   checkout's README when the step is run. Record the three reported lines in the Result. This step
   is required: if the checkout is unavailable, the plan stays incomplete and is reported to the
   owner, not archived.

Completion: the marker test passes and the three template runs report `missing`, `present` and
`present`.

### Increment C — Cross-references and records

Dependencies: B
Affected areas: `README.md`, `skills/knowledge-base-authoring/SKILL.md`,
`docs/decisions/0008-knowledge-base-skills-are-thin-wrappers.md`,
`docs/specs/knowledge-base-skills.md`, `docs/roadmaps/knowledge-base-skills.md`

1. Make the edits scoped above.
2. Run the suite, which includes the authoring-skill wiring test, then `python3 install.py` and
   `python3 install.py --check`.

Completion: the grep in the completion criteria lists only the intended references and the checks pass.

## Verification

- `python3 -B -m unittest discover -s tests` after each increment.
- `python3 install.py --check`, a scratch-destination install to confirm neither skill is created and the
  marker is, and the throwaway template run for the marker.
- `git diff --check`.
- An independent `workflow-reviewer` pass on the combined diff before the final commit.

## Risks and sensitive actions

- The marker is the one file the template installer reads outside a project. Its content is fixed and
  contains no machine state; the template treats it as untrusted and size-limited.
- The authoring skill's pointer changes the instructions a skill gives. The change is one sentence and
  the existing wiring test for that skill runs.
- `~/.claude/skills/second-opinion` and `~/.claude/skills/knowledge-base` remain until the owner
  removes them from their own shell (raw `rm` is denied to the agent, and the plan runs no deletion
  there; the owner may use `! rm -r` on exactly those two paths). Until then projects with the module
  would load two copies.
- Commits and the push need the owner's approval, as usual.

## Deferred work

- `REVIEWER_FACING_PATHS` in `hooks/codex_approver.py` names `skills/second-opinion/*`; in a project that
  installed the module the path is `.claude/skills/second-opinion/`. Whether to rename the entry is a
  separate decision with its own tests (ADR 0007).
- The remaining template-roadmap work (none is left after this plan) and the merge-versus-split review
  after candidate 6 of the knowledge-base roadmap.

## Result

Completed 2026-10-19. The plan was committed as `11ee372`; all three increments landed in one
commit, `2ebec56`, at the owner's request.

- **A:** `skills/second-opinion/` and `skills/knowledge-base/` were removed with their manifest lines
  and `tests/test_knowledge_base_skill_wiring.py`; `tests/test_second_opinion_wiring.py` kept the
  helper, installer and permission checks and the spec cross-link and dropped the skill checks.
  A scratch-destination `python3 install.py` created neither skill.
- **B:** the tracked `global-config.json` (`{"schema": 1}`) is listed in the manifest and installed
  into `~/.claude`; `tests/test_global_config_marker.py` pins its format. Template checkout
  `../claude_project_template` at `9b0decb`, new-project `--dry-run --with graphify --harness claude`:
  `--global-config` naming an empty scratch directory reported `graphify: global configuration: missing`;
  naming a scratch directory with a copy of the marker reported `present`; with no option (the real
  `~/.claude`) reported `present`.
- **C:** `README.md`, the `knowledge-base-authoring` pointer, a dated note on ADR 0008 and on the
  knowledge-base spec, and the knowledge-base roadmap were updated.

Verification: the full suite passed (925 tests, 5 skipped); `python3 install.py --check` reports a
match; `git diff --check` was clean. One failure occurred in the middle: the authoring skill's wiring
test allows only the flags the skill may run, and the first wording of the new pointer named
`--harness`; it was reworded without the flag and the suite then passed. An independent read-only
`workflow-reviewer` pass found no blocking findings. Its minor notes: the two `second-opinion` specs
(`second-opinion-plan-review.md`, `second-opinion-document-review.md`) still describe the skill as
living here and received no dated note, the skill prose checks are no longer pinned in this
repository, and the grep in the completion criteria also lists those specs and ADR 0007, which
describe the skill and are historical. The owner removed the two `~/.claude` skill directories.

Deferred, unchanged: the `skills/second-opinion/*` entry in `REVIEWER_FACING_PATHS`
(`hooks/codex_approver.py`), which names a path that exists only in projects that installed the
`codex` module as `.claude/skills/second-opinion/`.

### Codex plan review

## Codex plan review

- Plan: docs/plans/next.md (key 636943a2c9cd0a57)
- Rounds used: 3 of 3
- Round 1: model gpt-5.6-luna, effort low, 1 finding(s) (1 blocker or major), 89713 input and 1540 output tokens
- Round 2: model gpt-5.6-luna, effort low, 1 finding(s) (1 blocker or major), 114622 input and 1699 output tokens
- Round 3: model gpt-5.6-luna, effort high, 4 finding(s) (3 blocker or major), 657141 input and 9595 output tokens
- Outcome: not converged (3 blocker or major finding(s) in the last round)
- Effort raised to high for round 3: round 3 reached (round 3 of this review window)
- Decisions: 5 applied, 0 rejected
