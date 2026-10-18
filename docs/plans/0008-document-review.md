# 0008: Second-opinion review of specs and roadmaps

Status: Completed
Created: 2026-10-17
Completed: 2026-10-17

## Outcome

`ask-codex` and the `second-opinion` skill run the same bounded, read-only
Codex review loop on a spec (`docs/specs/*.md`) and a roadmap
(`docs/roadmaps/*.md`) as they do on `docs/plans/next.md`, with plan review
behavior unchanged.

## Scope

Implements `docs/specs/second-opinion-document-review.md` (Approved
2026-10-17); its decisions 1–13 are the governing requirements.

- `bin/ask-codex`: per-kind document handling; `review-spec` and
  `review-roadmap`; `--spec`/`--roadmap` on the per-document commands.
- New kinds `ask-codex/kinds/spec-review/` and `roadmap-review/`; manifest.
- `settings.json` permission entries and the `ask-codex-archive` approver rule.
- `skills/second-opinion/SKILL.md`, the plan-review spec cross-reference, and
  `README.md`.
- Mirror into `~/.claude` through `install.py`.
- Separate repository `claude_project_template`: guidance slots of the
  `plan-review` and `codex` modules (documentation only, own commit).

## Non-goals

- Any change to plan-review behavior, state, gates, or prompt.
- Automatic triggers, ADR/diff/code review, Codex writing files.
- New approver path logic; the helper alone validates paths.
- A helper copy or code in the template.

## Assumptions

- Verified: `bin/ask-codex` hard-codes `KIND`, `DEFAULT_PLAN`,
  `STATE_DIR_RE`, `resolve_plan` (needs `Created:`, rejects the empty template),
  `create_state_directory`, and the `{{PLAN_PATH}}` substitution; kinds are
  otherwise directory-driven (`load_kind(name)`).
- Verified: the only approver rule for `ask-codex` is
  `codex-approver/rules/ask-codex-archive.json` (flags table lists `--plan`);
  `settings.json` allows `review-plan`, `decide`, `status`, `models`, `init`
  and gates `extend`, `reset`, `prune`, `archive`.
- Verified: the template's `plan-review` and `codex` modules contain only
  guidance slots. `claude_project_template` currently has untracked
  `docs/roadmaps/` and `docs/specs/`; they are the owner's work and are not
  touched or committed here.
- Existing tests (`tests/test_ask_codex.py` and the others) must pass
  unmodified apart from additions.
- Editing `settings.json` and `codex-approver/` is policy-sensitive; each such
  change is shown in the diff for review before any commit.
- Real Codex runs send the reviewed file to OpenAI. Only non-secret sample
  documents are used.

## Discovery and impact evidence

Graphify: skipped — the graph is missing (`graph-status`: `missing`) and the
scope is enumerated by direct search: `grep` for `ask-codex|review-plan|
second-opinion` lists `bin/ask-codex`, `settings.json`, `install.py`,
`config-manifest.txt`, `codex-approver/` (rule and rubric),
`hooks/codex_approver.py`, `skills/second-opinion/SKILL.md`, `README.md`, the
specs/ADRs/plans (documentation only), and nine test files. `install.py` and
`hooks/codex_approver.py` reference the helper generically and are expected to
need no edit; Increment D confirms this by test.

## Completion criteria

The spec's acceptance criteria 1–8 are met with the evidence listed per
increment, `git diff --check` is clean, and `install.py --check` reports no
drift for both repositories.

## Increments

### Increment A — Helper handles three document types

Dependencies: None
Affected areas: `bin/ask-codex`, `tests/test_ask_codex.py`,
`tests/fixtures/fake_codex`

1. Write failing tests first (fake `codex`): `review-spec` and
   `review-roadmap` run a round, converge, and stop at the bound; refuse a
   path outside the allowed directory, a symlink, `README.md`, a subdirectory
   file, `docs/roadmaps/archive/*`, and a non-`.md` file; accept any document
   status; use state directories `.debug/<date>-spec-review[-N]/` and
   `-roadmap-review`; keep two kinds' reviews separate; reuse an open review;
   start a fresh review (bound 3) after `archive`; leave an orphaned open
   review after a rename and report it in `status`; `prune` handles all three
   directory families; the Codex argv is identical in shape to plan review.
2. Introduce a small per-kind table (kind name, subcommand, flag, allowed
   directory, state suffix, identity function) and thread it through
   `resolve_*`, `find_state`, `new_state` (`kind` recorded),
   `create_state_directory`, `STATE_DIR_RE`, and prompt building
   (`{{DOC_PATH}}` and `{{PLAN_PATH}}` both substituted). Plan identity and
   the closed-review rule stay exactly as they are; spec/roadmap identity is
   the repository-relative path, and a closed review does not match.
3. Add `review-spec --spec PATH` and `review-roadmap --roadmap PATH` (path
   required), and mutually exclusive `--plan`/`--spec`/`--roadmap` on `status`,
   `init`, `decide`, `extend`, `reset`, `archive`.
4. Run `python3 -m unittest tests.test_ask_codex` (or the repository's
   documented test command in `README.md`).

Completion: new tests pass; every pre-existing test passes unmodified;
criteria 1–4 of the spec evidenced.

### Increment B — Kind definitions and installer registration

Dependencies: A
Affected areas: `ask-codex/kinds/spec-review/`, `ask-codex/kinds/roadmap-review/`,
`config-manifest.txt`, `tests/test_install.py`

1. Write a failing manifest/install test for the six new files.
2. Add `kind.json`, `schema.json` (copy of plan-review's), and `prompt.md` per
   kind, with the review criteria in the spec's "Review criteria" section and
   the shared rules from the plan prompt.
3. Register the files; run `python3 install.py --check` (drift expected until
   the owner approves applying it), then apply after approval.

Completion: tests pass; `install.py --check` clean after apply; criterion 5
(files part) evidenced.

### Increment C — Permission and approver rules

Dependencies: A
Affected areas: `settings.json`, `codex-approver/rules/ask-codex-archive.json`,
`codex-approver/rubric.md` (only if it names the flags),
`tests/test_permissions.py`, `tests/test_codex_approver_archive.py`,
`tests/test_codex_approver_rules.py`

1. Write failing tests: `review-spec`/`review-roadmap` are allowed like
   `review-plan`; `archive`/`extend`/`reset`/`prune` stay gated; the archive
   rule accepts `--spec`/`--roadmap` as value flags and still rejects unknown
   flags.
2. Add the allow entries and flag-table entries; make no other rule change.

Completion: tests pass; the diff touches only the listed entries; criterion 5
(rules part) evidenced.

### Increment D — Skill and documentation

Dependencies: A, B, C
Affected areas: `skills/second-opinion/SKILL.md`,
`docs/specs/second-opinion-plan-review.md`, `README.md`,
`tests/test_second_opinion_wiring.py`

1. Write failing wiring assertions (skill names `review-spec`,
   `review-roadmap`, no status gate for them, the never-`archive`-to-get-
   around-a-bound rule, edit-only-the-reviewed-document rule).
2. Update the skill description and body; add a short pointer in the plan
   review spec ("Review kinds") and the README.
3. Run the wiring and install tests.

Completion: tests pass; the skill still gates plan review on `Proposed`.

### Increment E — Real runs, security review, and mirror

Dependencies: A–D
Affected areas: none beyond verification (state under untracked `.debug/`)

1. After owner approval, run exactly one real round of each new kind (two
   Codex requests; the helper's single automatic retry is the only permitted
   repeat, so at most four calls) on a throwaway sample spec and roadmap with no
   secrets; confirm valid JSON output. Stop on any failure or on a blocker or
   major finding; do not loop to convergence.
2. Run the `security-review` skill (and `security-reviewer` for hostile path
   probes: `..`, symlinks, absolute paths, control characters, `.md` look-alikes)
   on the new path-resolution code.
3. Apply `install.py` to `~/.claude` after approval and re-run `--check`.

Completion: criteria 6 and 8 evidenced; no unresolved Critical/High finding.

### Increment F — Template guidance (separate repository)

Dependencies: D
Affected areas: `claude_project_template/modules/plan-review/slots/`,
`claude_project_template/modules/codex/slots/`,
`claude_project_template/tests/test_install.py`

1. Write failing test assertions for the new guidance phrases in the
   generated `AGENTS.md` for `plan-review` and `codex`.
2. Edit the slots: tool-neutral spec/roadmap review guidance (on request, any
   status, read-only, bounded) in `plan-review`; `review-spec`/`review-roadmap`
   commands in `codex`.
3. Run the template's own test command; commit only exact paths there with its
   own approval, leaving the untracked `docs/` work alone.

Completion: template tests pass; criterion 7 evidenced.

## Verification

`python3 -m unittest discover -s tests` in this repository (confirm the exact
command from `README.md` first), `python3 install.py --check`, the template's
tests, `git diff --check`, and the real runs in Increment E.

## Risks and sensitive actions

- Editing `settings.json` and approver rules changes permissions: reviewed
  diff, no widening beyond the two new review subcommands.
- New path-resolution code is a security surface (Increment E review).
- Real Codex runs send file contents to OpenAI (non-secret samples only).
- Applying `install.py` changes `~/.claude`; the template commit is in
  another repository. Each commit uses `claude-workflow commit` after explicit
  approval; nothing is pushed.

## Deferred work

None identified.

## Result

All six increments are complete and verified. Commits: `000ffbd` in this repository
(helper, kinds, rules, skill, docs, tests, design spec); the template guidance is a
separate commit in `claude_project_template`.

Spec acceptance criteria (`docs/specs/second-opinion-document-review.md`):

1. Shared loop with a fake `codex`: bound and ceiling, undecided-findings refusal,
   convergence, re-raise suppression and escalation, exact Codex arguments, for both
   new kinds (`tests/test_ask_codex_documents.py`).
2. Path refusals and plan behavior unchanged: the 138 existing `tests/test_ask_codex.py`
   tests pass unmodified.
3. Any status accepted; a fresh review after `archive` for spec and roadmap; a closed
   plan review still blocks.
4. Separate state directories; `prune` covers all three families.
5. Installer: `install.py --check` clean after apply; allow entries and the archive
   approver rule tested.
6. Real runs (`gpt-5.6-luna`, `low`): one `review-spec` round on a throwaway sample spec
   returned valid JSON with two major findings; one `review-roadmap` round converged. Two
   Codex requests, no retries. The samples were removed afterwards.
7. Template guidance edits pass the template's 85 tests.
8. Security review: no Critical or High finding. Four findings fixed with regression
   tests (README in any case, symlinked parent of the document directory, empty document
   flag falling back to the plan, placeholder expansion through a file name) plus a
   hard-link refusal. Not covered: Unicode look-alike names and a race between validation
   and Codex reading the file.

An independent read-only review found no Critical or High issue; its Medium finding (an
orphaned spec/roadmap review could not be closed) and four Low findings were fixed or
documented. Final suite: 902 tests, 5 skipped; `git diff --check` clean.

Deviations from the approved design: the approver's evidence collector (`collect_archive`)
needed a small change to forward `--spec`/`--roadmap` to `status` (design decision 11
amended); orphaned open reviews are archived by naming their old path (decision 9
amended). Plan review of this plan was not requested (Second opinion: not requested).

Residual: `archive` prints its summary once for a spec or roadmap review; the stale
2026-10-16 plan-review state for plan 0007 was closed with `ask-codex archive` when this
plan was archived (its summary was not added to plan 0007).
