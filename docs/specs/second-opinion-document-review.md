# Second opinion: bounded Codex review of specs and roadmaps

Status: Accepted (2026-10-17); implemented and verified
Date: 2026-10-17

## Purpose

`ask-codex` and the `second-opinion` skill give the owner a bounded,
read-only Codex review loop for `docs/plans/next.md`
(`second-opinion-plan-review.md`). The owner also writes specifications
(`docs/specs/`) and roadmaps (`docs/roadmaps/`) as defined by
`claude_project_template`, and wants the same independent second opinion on
them, with the same bounded loop, so those documents are checked before plans
are built on them.

## Scope

- Two new review kinds, `spec-review` and `roadmap-review`, each a directory
  under `ask-codex/kinds/` with its own `kind.json`, `prompt.md`, `schema.json`
  (the schema may be identical to `plan-review`'s).
- Two new subcommands, `review-spec --spec PATH` and
  `review-roadmap --roadmap PATH`, beside `review-plan`.
- The existing shared loop applies unchanged: bound (default 3, ceiling 5),
  `decide`, ledger, re-raise suppression and escalation, effort escalation,
  retry and failure cap, `extend`/`reset`/`archive`/`prune` as owner-only.
- `second-opinion` skill extended to all three document types.
- The same change mirrored into `~/.claude` and into the template's
  `plan-review` and `codex` modules (`claude_project_template`).

## Non-goals

- Automatic triggers. Reviews run only when the owner asks.
- Reviewing diffs, code, or free-form questions. (ADRs were a non-goal here and
  are added by plan 0011; see "ADR review" below.)
- Codex writing any file. Claude edits only the document under review.
- Any change to plan review behavior, its gates, or its state.
- Judging whether a roadmap or spec is *approved*; review never changes a
  document's status.

## Decisions (owner)

| Topic | Decision |
|---|---|
| Loop | Same bounded loop as plans, not a lighter pass |
| Status gate | None. A spec or roadmap is reviewable whenever the owner asks, at any status |
| Trigger | On request only |
| Restart after `archive` | A spec or roadmap review may be restarted after `archive` with a fresh default bound (3). `archive` stays owner-prompted; the skill forbids using it to get around a bound. Extra rounds still come only from `extend` or `reset` |

## Decisions (assistant's calls, for the owner to check)

1. **Command shape:** separate `review-spec` / `review-roadmap` subcommands
   with `--spec` / `--roadmap` path flags, not a generic `review --kind`.
   `--spec` and `--roadmap` have no default path (a spec or roadmap is always
   named); `--plan` keeps its `next.md` default.
2. **Path restriction:** `--spec` must resolve under `docs/specs/` and
   `--roadmap` under `docs/roadmaps/` (excluding `README.md` and `archive/`
   for roadmaps), in addition to the existing in-repository, non-symlink,
   regular-file, size, and text checks. This keeps a review request from
   pointing Codex at an arbitrary file.
3. **Identity:** plans are keyed by title + `Created:`. Specs and roadmaps have
   no `Created:` line, so their key is the repository-relative path. An open
   review belongs to its file (as plans already do).
4. **Living documents can be reviewed repeatedly:** a *closed* review does not
   block a new one for a spec or roadmap. `review-*` on a document whose only
   review is closed starts a fresh review with a fresh bound. Plans keep the
   current rule (a closed plan review stays closed). Because a closed spec or
   roadmap review is no longer found, `archive` prints its summary only once for
   those kinds. The cross-review "another review has used its full bound"
   warning considers only reviews of the same kind.
5. **State directories:** `.debug/<date>-spec-review[-N]/` and
   `.debug/<date>-roadmap-review[-N]/`; `state.json` records its `kind`.
   `prune` considers all three directory families.
6. **Empty-template and `Created:` checks** stay plan-only. Spec and roadmap
   checks require non-empty text and a top-level heading only.
7. **Archive output:** `archive` prints a summary headed with the kind. It is
   run only when the owner asks; a spec/roadmap review is not tied to a plan
   archive. Recording the outcome is optional for specs and roadmaps (a
   "Second opinion" note is not added to the template formats).
8. **Rejection reasons** and findings handling are unchanged.
9. **Rename or move:** an open review stays matched by recorded path (or
   `samefile`), as plans are today. After a rename the old review is not
   followed: `review-*` on the new path starts a new review, and the old one
   remains open until the owner archives or prunes it. A second open review
   whose path no longer exists is reported in `status` as orphaned. `status`,
   `decide`, `extend`, `reset`, and `archive` accept the exact recorded path of
   such an open review although the file is gone (and only then), so the owner
   can archive it; `init` and `review-*` still refuse a missing file. If an open
   review exists for the path, `review-*` resumes it; when both a closed and an
   open review match, the open one wins.
10. **Allowed paths:** `--spec` accepts only a regular `.md` file directly in
    `docs/specs/`; `--roadmap` only directly in `docs/roadmaps/`. `README.md`
    (in any letter case) and subdirectories (including
    `docs/roadmaps/archive/`) are refused, as is a hard-linked file, and no
    component of the document directory (`docs`, `docs/specs`) may be a
    symlink. An empty `--spec ""` or `--roadmap ""` is a usage error and never
    falls back to the plan. (Added after the adversarial path review.)
11. **Approver and permission rules:** the Codex approver matches the
    subcommand and a declared flag table, and its existing rules list
    `--plan`. The `ask-codex-archive` rule gains `--spec` and `--roadmap` as
    value flags; the helper alone validates the path. The approver's evidence
    collector (`collect_archive`) runs `ask-codex status` itself, so it
    forwards whichever one document flag was given (two fail closed); that is
    the only approver code change and adds no path logic. The rubric wording
    is corrected, since a closed spec or roadmap review may be followed by a
    fresh one.
12. **Schemas and prompts:** the new kinds copy `plan-review`'s schema (each
    kind stays self-contained and the manifest lists real files). The new
    prompts use `{{DOC_PATH}}`; the helper substitutes both `{{DOC_PATH}}` and
    `{{PLAN_PATH}}`, and the `plan-review` prompt is not migrated.
13. **Template mirror:** `claude_project_template`'s `plan-review` and `codex`
    modules hold only guidance slots (no helper copy), so that change is
    documentation only. It is a separate commit in that repository and is
    checked with its own installer tests. `archive` output stays on stdout, as
    for plans.

## Review criteria (the prompts)

Both prompts keep the plan prompt's rules: read-only, review only the named
file, stay inside the repository, do not invent problems, severities as
defined, structured JSON output.

**Spec review** judges, per `claude_project_template` `docs/specs/README.md`:
stated scope and non-goals; assumptions and constraints; acceptance criteria
that are observable and testable; requirements that are unambiguous and
non-contradictory; consistency with accepted ADRs and the repository's own
instructions and files it names; no implementation sequencing (belongs in a
plan) and no work log (a spec is updated in place); no unverified claims about
existing behavior.

**Roadmap review** judges, per `docs/roadmaps/README.md`: status and updated
date; purpose and current state that match the repository; ordered plan
candidates each with outcome, dependencies, boundary, and promotion trigger;
a sound order and acyclic dependencies; candidates at plan-boundary level
without file lists, acceptance criteria, or commands (those belong in the
promoted plan); deferred work; consistency with ADRs; no text that reads as
authorization to implement.

## Components changed

| Component | Change |
|---|---|
| `bin/ask-codex` | Parametrize `KIND`, document resolution, state-directory naming/matching, prompt placeholder (`{{DOC_PATH}}`, keeping `{{PLAN_PATH}}` working), and identity key by kind; add two subcommands |
| `ask-codex/kinds/spec-review/`, `roadmap-review/` | New prompt, schema, `kind.json` |
| `config-manifest.txt`, `install.py` | Register the new kind files; `--check` clean |
| `settings-policy.txt` / `codex-approver` rules | Allow the new bare subcommands exactly as `review-plan` is handled; `archive`/`prune`/`extend`/`reset` stay gated |
| `skills/second-opinion/SKILL.md` | Cover the three document types, no status gate for spec/roadmap, edit-only-the-reviewed-document rule, and never run `archive` to get around a bound |
| `tests/test_ask_codex.py`, `test_second_opinion_wiring.py` | Cover the new kinds |
| `docs/specs/second-opinion-plan-review.md` | Note the extension and link here |
| `claude_project_template` `modules/plan-review`, `modules/codex` | Neutral and Codex-specific guidance for spec/roadmap review |

## Acceptance criteria

1. With a fake `codex`, tests prove for each new kind: bound and ceiling,
   refusal with undecided findings, convergence, re-raise suppression, and the
   exact Codex arguments, using the shared loop code.
2. `review-spec` / `review-roadmap` refuse paths outside their directory,
   symlinks, `README.md`, and `archive/` entries; `review-plan` behavior and
   state are unchanged (existing tests pass unmodified).
3. A review of a spec or roadmap at any status is accepted; after `archive`, a
   new review of the same file starts fresh; a closed plan review still does
   not.
4. State directories for the three kinds are kept apart; `prune` previews and
   deletes only closed ones among all three families.
5. The installer places the new kind files; `--check` reports no drift; the
   permission and approver rules treat the new subcommands like `review-plan`.
6. A real run of each kind against a sample spec and roadmap returns valid
   JSON.
7. The template modules describe the new reviews and the template's own
   installer tests pass.
8. A security review covers the new path-resolution surface.

## Left to the builder

Internal refactoring of the helper, the exact prompt wording, test layout, and
the precise approver-rule edits, provided the decisions above hold.

## Related

`second-opinion-plan-review.md`; ADR 0001; `claude_project_template`
`docs/specs/README.md` and `docs/roadmaps/README.md`.

## ADR review (plan 0011)

An ADR in `docs/decisions/` is reviewed like a spec or roadmap: the
`adr-review` kind (`ask-codex/kinds/adr-review/`), `review-adr --adr PATH`, and
`--adr` on `status`, `init`, `decide`, `extend`, `reset` and `archive`. The path
must be a `.md` file directly in `docs/decisions/`, not `README.md`; the same
in-repository, non-link, regular-file and size checks apply. An ADR has no
`Created:` line, so its key is its repository-relative path, and a closed
review never blocks a fresh one. State lives in
`.debug/<date>-adr-review[-N]/`. The prompt asks the reviewer to judge that the
ADR states context, decision, alternatives and consequences, that its claims
about the repository are true, and that it does not contradict an earlier ADR
it does not supersede; it does not ask whether the decision is the right one
beyond its consistency and cited evidence. The approver's `ask-codex-archive`
rule accepts `--adr` as a value flag like the other document flags; nothing
else about the approver changed.
