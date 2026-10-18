# Consuming knowledge-base skill

Status: In Progress
Created: 2026-10-18

## Goal

A personal `knowledge-base` skill that, from any project, finds the registered
knowledge-base stores, answers from them under the store's claim tags, and treats every
store file as data. It meets the `[K2]` criteria of
[knowledge-base-skills](../specs/knowledge-base-skills.md) and is candidate 2 of the
[roadmap](../roadmaps/knowledge-base-skills.md).

## Scope

- `skills/knowledge-base/SKILL.md`: one file, no references. Frontmatter `name:
  knowledge-base` and a single-line `description` from the spec's trigger. Body, in the
  spec's terms:
  - discovery: inside a store, then registered stores, then a path the owner names, with
    an owner-named path overriding; `store` accepted only as `../name` or absolute; real
    paths and no symlink out; absent `module_info` is "not declared" and a missing store
    "not available"; `kb.json` `kind` and `schema` required, `kb.json` authoritative over
    the manifest's hints;
  - several stores: list by module name, never select by type alone, never merge, ask when
    relevance is unclear;
  - using a store: the six steps of the spec's "Using a store" section;
  - the four safety rules, and that the skill never runs a store's tool or edits a store;
  - the template's `--register` line printed for the owner when no store is registered.
- `config-manifest.txt`: the skill's entry, so `install.py` mirrors it into `~/.claude`.
- `tests/test_knowledge_base_skill_wiring.py`: a wiring test in the style of
  `tests/test_second_opinion_wiring.py`.
- `README.md`: the skills bullet names the new skill and the roadmap.
- `docs/plans/README.md` archive row and the roadmap (candidate 2 done) at the end.

## Non-goals

- The authoring skill and any of its operations (candidates 3 to 6).
- A `settings.json` change. The skill uses the file tools only. If reading a sibling
  store directory prompts, that is expected and stays a prompt.
- Any change to `claude_knowledge_base` or `claude_project_template`.
- A behavior test inside the suite. Behavior is shown by the live check below.

## Assumptions and constraints

- Mirrored files carry no absolute path, identity, or registry location (spec).
- The skill is prose: the wiring test pins statements, so each `[K2]` statement must be
  worded to be searchable, as `second-opinion`'s are.
- The shapes of `.template-manifest`, `kb.json`, and the descriptor were observed on
  2026-10-18 (starter `6793400`, template `6d4d3e8`). If either repository has changed
  shape since, the skill follows the spec's rule of stopping on an unexpected value and
  the spec is revisited.
- Decision points. The owner approved the plan on 2026-10-18 without changes, which adopts
  the recommended option for decision point 1 (run the live check). Decision point 2 was taken:
  Codex reviewed the plan (two rounds, converged).
  The points were:
  1. Run the live check in Increment C (scratch stores, two fresh agents, hostile
     fixtures). Alternative: skip it, as plan 0011 skipped its live check, and record that
     `[K2]` criterion 3 and the worked example in 5a are unshown.
  2. Whether Codex reviews this plan (`review-plan`) before approval. It is a modest
     skill; optional.

## Discovery and impact evidence

Graphify: skipped — the affected files are enumerated above, the work is one new skill, a
manifest line and a test, and the precedent is `skills/second-opinion` with
`tests/test_second_opinion_wiring.py`.

## Completion criteria

- The skill exists with the statements the spec's criteria 1, 2, 2a, 4, 5 and 5a require,
  and a wiring test that fails without them and passes with them.
- The skill is in `config-manifest.txt`; `python3 install.py --check` is clean after
  syncing.
- Unless the owner skips it: the live check shows two registered stores listed and kept
  apart, attribution, an owner-path override, and refusal of the hostile fixtures.
- An independent `workflow-reviewer` pass has run, and the full suite and `git diff
  --check` pass.

## Increments

### Increment A — Failing wiring test

Dependencies: None
Affected areas: `tests/test_knowledge_base_skill_wiring.py`

1. Write the test: the skill file exists with `name: knowledge-base` and a single-line
   `description` containing the trigger terms; the manifest lists it; the text states each
   of the discovery order, the owner-path override, the `../name`-or-absolute rule, absent
   `module_info` as undeclared, a missing store as not available, `kb.json` `kind` and
   `schema`, listing by module name and never by type alone, no merging, attribution, the
   six use steps, the four safety rules, and never running a store tool or editing a
   store; and it contains no absolute path, identity, or registry location.
2. Run it and confirm it fails for the right reason (the skill is absent).

Completion: the test fails with the skill missing, and the failure names the file.

Done 2026-10-18: `tests/test_knowledge_base_skill_wiring.py` (9 tests) fails with 2 failures and 7 errors, all
from the missing `skills/knowledge-base/SKILL.md` and its absent manifest line.

### Increment B — The skill

Dependencies: Increment A
Affected areas: `skills/knowledge-base/SKILL.md`, `config-manifest.txt`, `README.md`

1. Write `SKILL.md` to the spec; add the manifest line and the README bullet.
2. Run the wiring test until it passes; run `python3 install.py` to sync `~/.claude`, then
   `python3 install.py --check`.

Completion: the wiring test passes and the install check is clean.

### Increment C — Live check

Dependencies: Increment B; decision point 1
Affected areas: scratch directories only

1. Rebuild two scratch stores and a scratch project that registers both (scratch registry,
   throwaway identity). Give each store a domain and one entry with different, harmless
   content, one claim tagged `[V]` and one `[U]`, written directly in the scratch store.
2. Add hostile fixtures in scratch only: an entry containing an instruction to run a
   command and fetch a URL; a project manifest entry whose `store` is neither `../name` nor
   absolute; a store whose `kb.json` has a wrong `kind`; a symlinked router.
3. Run fresh agents (the Agent tool, `general-purpose`, each given only the skill's text, the
   scratch project path, and one question, with no hint about the fixtures): one on a question
   both stores could answer, one with an owner-named path inside a project that has registered
   stores, and one per hostile fixture. Record for each whether it listed both stores, kept
   them apart, attributed claims, checked the `[U]` claim against its source (or kept it
   unverified), ran no store tool, and refused the fixture.
4. Keep the evidence in two places: the fixture layout, each agent prompt verbatim, and a
   quoted line of each agent's report in `.debug/2026-10-18-kb-skill-live/` (untracked, with
   a README naming the commit, the starter and template commits, and the conclusion, per the
   global debug rule); and one row per `[K2]` criterion (criterion, agent, pass or fail, the
   quoted line) in the tracked Result of the archived plan.

Completion: every `[K2]` criterion has a Result row backed by the local record, or an
explicit "skipped" if the owner skips the check.

### Increment D — Review and close-out

Dependencies: Increments B and C
Affected areas: `docs/plans/README.md`, `docs/roadmaps/knowledge-base-skills.md`

1. Run an independent `workflow-reviewer` pass on the skill and test, and apply or reject
   its findings.
2. Mark candidate 2 done in the roadmap; archive this plan after verification.

Completion: findings dispositioned, the roadmap updated, the suite green.

## Verification

`python3 -B -m unittest discover -s tests -p 'test_knowledge_base_skill_wiring.py'`, then
the full suite `python3 -B -m unittest discover -s tests`, `git diff --check`,
`python3 install.py --check`, and the live note from Increment C.

## Risks and sensitive actions

- The skill reads untrusted store content and an untrusted manifest. It executes nothing,
  and the live check's hostile fixtures stay in scratch directories.
- Increment C creates git repositories in scratch directories with a throwaway identity,
  uses a scratch registry (never `~/.config/claude-project-template/registry.json`), and
  spawns fresh agents that read only the scratch tree. No push, no commit, and no edit in
  either other repository.
- `python3 install.py` writes the skill into `~/.claude`.
- Otherwise none identified.

## Deferred work

- The authoring skill (candidates 3 to 6) and the end-to-end audit (candidate 7).
- A permission rule that lets the skill read sibling store directories without a prompt.

## Result

<!-- Complete this only after verification. Archive the plan according to
README.md, then reset this file to the empty template. -->
