# 0011: Second-opinion review of ADRs

Status: Completed
Created: 2026-10-18
Completed: 2026-10-18

## Goal

`ask-codex` and the `second-opinion` skill run the same bounded, read-only
Codex review loop on an ADR (`docs/decisions/NNNN-*.md`) as they do on a spec or
roadmap, with a prompt that judges a decision record, and with plan, spec and
roadmap review behavior unchanged.

## Scope

Follows the pattern of plan 0008 (spec and roadmap kinds) and
`docs/specs/second-opinion-document-review.md`. An ADR is a living document: it
has no `Created:` line, so its identity is its repository path, and a closed
review never blocks a fresh one (the spec and roadmap rule).

- `bin/ask-codex`: an `adr-review` entry in `DOC_KINDS` (flag `adr`, directory
  `docs/decisions`, `README.md` refused), `review-adr --adr PATH`, `--adr` on
  the per-document commands (`status`, `init`, `decide`, `extend`, `reset`,
  `archive`) as a fourth member of the one-of group, `adr` in `STATE_DIR_RE`,
  and the module docstring and help text.
- New kind `ask-codex/kinds/adr-review/` (`kind.json`, `prompt.md`,
  `schema.json`, the schema identical to the roadmap kind's) and its
  `config-manifest.txt` entries.
- `settings.json`: allow `Bash(ask-codex review-adr:*)`, beside `review-spec`
  and `review-roadmap`. `archive` stays gated.
- Approver, because `archive` is delegable and must keep working for an ADR
  review: `--adr` in `codex-approver/rules/ask-codex-archive.json`, the flag
  tuple in `collect_archive` (`hooks/codex_approver.py`), and the
  `ask-codex-archive` rubric wording.
- `skills/second-opinion/SKILL.md` (table row, "ADR" wherever it says "spec or
  roadmap", the do-not-use-for-ADRs sentence removed), `README.md`, and
  `docs/specs/second-opinion-document-review.md` (extended to name ADRs).
- Tests: extend `tests/test_ask_codex_documents.py` (its per-kind table),
  `tests/test_codex_approver_archive.py`, and
  `tests/test_second_opinion_wiring.py`.
- Mirror into `~/.claude` through `install.py`.

## Non-goals

- Any change to plan, spec or roadmap review behavior, state or prompts.
- Codex writing or accepting an ADR, or review changing an ADR's `Status`.
- Automatic triggers, diff or code review, other document types.
- Changing `DELEGABLE` or any approver authority: the `ask-codex-archive` rule
  gains one value flag and nothing else.
- The `claude_project_template` guidance slots (separate repository, own
  change, after this one lands).

## Assumptions and constraints

- Verified: `DOC_KINDS` drives path resolution (`resolve_living_document`),
  labels and the ledger; `STATE_DIR_RE` and the `--plan/--spec/--roadmap`
  argument group are the other places the kind set is hard-coded.
- Verified: `collect_archive` names `--plan`, `--spec` and `--roadmap`
  explicitly, so the approver is not generic here. Without the change an
  `archive --adr` would be an unknown flag and fall back to the normal prompt
  (fail-safe), which is why it is in scope.
- ADR files live directly in `docs/decisions/`, are named `NNNN-*.md`, and have
  a `# ` heading. The existing resolver (a `.md` file directly in the
  directory, not `README.md`, not a hard link or symlink) fits unchanged.
- Decision for the owner at approval: the prompt checks that an ADR states
  context, decision, alternatives and consequences, that its claims match the
  repository, and that it does not contradict an earlier ADR it does not
  supersede. It does not judge whether the decision is the right one beyond
  internal consistency and stated evidence. Say so if you want a different
  stance.
- A real review sends the ADR to OpenAI; only a non-secret ADR is used for the
  live check, and only after the owner approves it.
- Editing `settings.json` and `codex-approver/` is policy-sensitive; each such
  change is reviewed in the diff before any commit.
- The `second-opinion` skill copy in `~/.claude` is changed only through
  `install.py`.

## Discovery and impact evidence

Graphify: skipped — the graph is missing (`graph_missing` on the last commit)
and the scope is enumerated by direct search: `grep` for
`roadmap-review|review-roadmap` lists `bin/ask-codex`, `settings.json`,
`config-manifest.txt`, `ask-codex/kinds/roadmap-review/`, `skills/second-opinion/SKILL.md`,
`docs/specs/second-opinion-document-review.md`, `README.md`, and the tests
`test_ask_codex_documents.py`, `test_second_opinion_wiring.py`,
`test_codex_approver_archive.py`; `collect_archive` in `hooks/codex_approver.py`
and the archive rule file were found by reading the approver path. Increment C
confirms nothing else by running the full suite.

## Completion criteria

- `ask-codex review-adr --adr docs/decisions/NNNN-x.md` runs a bounded round,
  with `status`, `init`, `decide`, `extend`, `reset` and `archive` accepting
  `--adr`; a path outside `docs/decisions/`, a `README.md`, a link or a second
  document flag is refused.
- After `archive`, the next `review-adr` of the same ADR starts a fresh review.
- Plan, spec and roadmap tests pass unmodified apart from additions.
- An approver test shows `ask-codex archive --adr <path>` handled like the spec
  and roadmap forms, and the rule still rejects an unknown flag.
- `python3 install.py --check` reports no drift; `git diff --check` is clean;
  the full test suite passes.
- An independent `workflow-reviewer` review has no unresolved material finding.

## Increments

### Increment A — The review-adr kind in the helper

Dependencies: None
Affected areas: `bin/ask-codex`, `ask-codex/kinds/adr-review/`,
`config-manifest.txt`, `tests/test_ask_codex_documents.py`

1. Extend the per-kind table in `test_ask_codex_documents.py` with an `adr`
   entry (flag `--adr`, directory `docs/decisions`, kind `adr-review`) and run
   it to see the new cases fail.
2. Add the `DOC_KINDS` entry, `STATE_DIR_RE`, `review-adr`, and `--adr` in the
   argument group; add `kind.json`, `schema.json` and the ADR `prompt.md`; add
   the manifest entries.
3. Run `python3 -m unittest tests.test_ask_codex tests.test_ask_codex_documents`.

Completion: the new ADR cases and every existing case pass.

### Increment B — Permissions, approver and guidance

Dependencies: Increment A
Affected areas: `settings.json`, `codex-approver/rules/ask-codex-archive.json`,
`codex-approver/rubric.md`, `hooks/codex_approver.py`,
`skills/second-opinion/SKILL.md`, `README.md`,
`docs/specs/second-opinion-document-review.md`,
`tests/test_codex_approver_archive.py`, `tests/test_second_opinion_wiring.py`

1. Add the failing approver and wiring tests first (an `--adr` archive is
   matched like `--spec`; `review-adr` is allowed and `archive` still gated).
2. Add the allow entry, the rule flag, the `collect_archive` flag tuple and the
   rubric wording; update the skill, README and spec.
3. Run `python3 -m unittest tests.test_codex_approver_archive
   tests.test_second_opinion_wiring`.

Completion: the new tests pass, the `ask-codex-archive` rule accepts `--adr` as
a value flag and still rejects an unknown flag, and no other approver behavior
changed.

### Increment C — Verification and review

Dependencies: Increments A and B
Affected areas: whole repository; `~/.claude`

1. `python3 install.py`, then `python3 install.py --check` and
   `git diff --check`.
2. Run the full suite (`python3 -m unittest discover tests`, long; use a
   generous timeout).
3. Run an independent `workflow-reviewer` review of the diff; apply or reject
   each finding with a reason and add a regression test for any real defect.
4. With the owner's approval, one live `review-adr` of a non-secret ADR to see
   a real round converge or return findings.

Completion: all checks pass, review findings are resolved or recorded, and the
live check is run or recorded as not run.

## Verification

- `python3 -m unittest tests.test_ask_codex tests.test_ask_codex_documents
  tests.test_codex_approver_archive tests.test_second_opinion_wiring` for the
  touched areas; the full suite before completion.
- `python3 install.py --check` proves the mirror matches; `git diff --check`
  proves whitespace.
- The live review proves the prompt and schema work end to end with Codex; it
  is not part of the automated suite.

## Risks and sensitive actions

- Policy-sensitive files: `settings.json` and `codex-approver/` change. The
  approver gains one flag on an existing delegable rule; the ceiling does not
  move. A mistake would make an ADR archive prompt instead of auto-approving,
  or accept a flag it should not, which the unknown-flag test guards.
- Real Codex runs send the ADR to OpenAI; use a non-secret ADR and only with
  approval.
- A prompt that is too strict or too loose produces noisy or empty reviews;
  the live check is the only evidence on that, and the prompt is easy to revise
  afterwards.
- No commit, push or install beyond `install.py` happens without separate
  approval.

## Deferred work

- `claude_project_template` guidance slots for ADR review (separate repository).
- Tuning the ADR prompt after a few real reviews.

## Result

Increment A: the `adr-review` kind (`DOC_KINDS`, `STATE_DIR_RE`, `review-adr`, `--adr` on the per-document commands,
`title_case` so the ledger label stays `ADR`), `ask-codex/kinds/adr-review/`, manifest entries. Increment B: `review-adr`
allowed in `settings.json` (`archive` still gated), `--adr` value flag on the `ask-codex-archive` rule and in
`collect_archive`, rubric, skill, README and spec wording. Tests extended in `test_ask_codex_documents.py`,
`test_codex_approver_archive.py` and `test_second_opinion_wiring.py`. `DELEGABLE` and the approver's output shape are
unchanged. Commits: `d738003` (plan), `0cc39dc` (implementation), `2c87817` (status).

Verification: full suite 914 tests, 5 skipped, 0 failed; `git diff --check` clean; `install.py --check` no drift. An
independent `workflow-reviewer` pass found no material defect; it read the path-confinement code but ran no hostile
paths, and the generic per-kind tests (now including `adr`) are the executable evidence for them.

Not done: the live `review-adr` of a real ADR through Codex was skipped at the owner's direction, so the ADR prompt is
untested against Codex. No Codex review of this plan was run, so there is no `ask-codex archive` summary.

Residual risk: the prompt may prove too strict or too loose; revise it after the first real review.
