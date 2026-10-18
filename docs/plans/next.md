# Knowledge-base skills specification and decision

Status: In Progress
Created: 2026-10-18

## Goal

Fix, in a reviewed specification and an ADR, how the personal knowledge-base skills
are shaped, so each later skill is a plan with testable criteria instead of a
design argument. This is candidate 1 of
[knowledge-base-skills](../roadmaps/knowledge-base-skills.md).

## Scope

- `docs/specs/knowledge-base-skills.md`: the specification, covering:
  - the skill set: how many skills, their names, and one trigger description each;
  - store discovery: reading `module_info` in `.template-manifest`, listing every
    `type: knowledge-base` entry by module name, `kb.json` as the root marker inside
    a store, the consumer rules from the template README, and the rule that a skill
    that writes never defaults to a store when several exist;
  - starter checkout discovery for create and upgrade;
  - the wrapper rule: a skill reads the store's `docs/kb/` and `AGENTS.md` first and
    links the procedure instead of copying it, restating only the safety rules
    (untrusted data, delegated output stays `[U]` or `[A]`, quarantine);
  - a permission table per skill: what runs without asking, what prompts, and what
    needs the owner (creating a directory, a git identity, registering with the
    template, releasing a quarantined source, any commit or push);
  - acceptance criteria for roadmap candidates 2 to 7, each tagged with the
    candidate that delivers it.
- `docs/decisions/0008-knowledge-base-skills-are-thin-wrappers.md`: the ADR for the
  wrapper rule and the discovery contract, with alternatives (copy the procedure into
  skills, ship skills inside the store, one skill with modes).
- Index rows in `docs/specs/README.md` and `docs/decisions/README.md`.
- Roadmap update: mark candidate 1 done and record the owner's decisions; adjust
  later candidates only where the spec changes their boundary.

## Non-goals

- Any skill file, `settings.json` change, manifest entry, or helper. Those belong to
  candidates 2 to 7.
- Changing `claude_knowledge_base` or `claude_project_template`. If the spec finds a
  gap in either, record it as a request for the owner.
- Accepting the ADR without explicit approval.

## Assumptions and constraints

- Verified: the template records `module_info` per module and, for external modules,
  `store` (`../name` or an absolute path); the knowledge-base descriptor declares
  `type: knowledge-base` with `data.router` and `data.spec`; a project may hold several
  stores. The `.kb-manifest` records `starter_commit` and `starter_dirty` but no
  checkout path (read in `claude_knowledge_base/install.py`), so a skill cannot recover
  the checkout from a store.
- Not verified: that `kb.json` marks the store root in practice (the format spec
  says it is the identification marker); the spec's discovery rule must be checked
  against a real created store in Increment A.
- Mirrored files carry no machine-specific path or identity.
- The store's tools and docs are the authority for the store's version; a skill never
  assumes the checkout's version matches the store.
- Decision points. The owner approved the plan on 2026-10-18 without changes, which
  adopts the recommended option (listed first) for each:
  1. Skill set: two skills, `knowledge-base` (consume, used from any project) and
     `knowledge-base-authoring` (create, upgrade, domain, wave, expand, used inside a
     store). Alternatives: five skills, one per operation; or one skill with modes.
  2. Starter checkout: the skill asks the owner for the path and verifies it
     (`install.py` and `kit/kit.json` present) before running anything. Alternative:
     also honor an environment variable.
  3. Procedure text: link to the store's `docs/kb/` and restate only the safety
     rules. Alternative: summarize the operations in the skill.
  4. Whether Codex reviews the spec and the ADR (`review-spec`, `review-adr`) before
     acceptance. Recommended: yes, as these are the first uses of both on this topic.

## Discovery and impact evidence

Graphify: skipped — documents only; the affected files are enumerated above and the
precedents are the `second-opinion` skill, its spec, and ADRs 0001 and 0004 to 0007.

## Completion criteria

- The spec and the ADR exist, are reviewed, and every decision point above is recorded
  as decided.
- Each of roadmap candidates 2 to 7 has acceptance criteria in the spec that name it.
- The discovery rule is checked against a real store created in a scratch directory
  and registered with a scratch project (read-only use of the other repositories'
  installers, nothing committed there).
- The ADR is `Proposed` unless the owner accepts it. `git diff --check` and the full
  suite pass.

## Increments

### Increment A — Check the discovery contract

Dependencies: None
Affected areas: none tracked; scratch directories only

1. Create a store with `claude_knowledge_base/install.py` in a scratch directory with
   an explicit throwaway identity, and register it with a scratch project through the
   template's `install.py --register`. Do this twice to get two stores.
2. Read `.template-manifest` and the store's `kb.json`, and record what a skill would
   see: the `module_info` entries, `store` values, descriptor `data`, and whether
   `kb.json` marks the root.

Completion: a written note of the observed manifest shape, kept for Increment B; any
mismatch with the roadmap's assumptions is listed for the owner.

Done 2026-10-18: the note is in the session scratchpad (`incA/NOTE.md`) and its findings are
summarized for the owner; the `kb.json` root marker is confirmed.

### Increment B — Specification

Dependencies: Increment A, and the owner's answers to the decision points
Affected areas: `docs/specs/knowledge-base-skills.md`, `docs/specs/README.md`

1. Write the spec with the sections listed under Scope, using the observed manifest
   shape from Increment A.
2. Run `ask-codex review-spec` on it, applying or rejecting each finding, and update
   the index.

Completion: the spec has no placeholders, each acceptance criterion names its
candidate, and the review converged or its remaining disputes are listed.

Done 2026-10-18: the spec was reviewed for four rounds (the bound extended once); every finding was
applied, and the last round's fixes were not re-reviewed. The owner approved the spec.

### Increment C — ADR and roadmap

Dependencies: Increment B
Affected areas: `docs/decisions/0008-knowledge-base-skills-are-thin-wrappers.md`,
`docs/decisions/README.md`, `docs/roadmaps/knowledge-base-skills.md`

1. Write the ADR as `Proposed` through the `architecture-decisions` skill, run
   `ask-codex review-adr`, and update the index.
2. Update the roadmap: candidate 1 done, decisions recorded, later boundaries adjusted
   only where the spec requires.

Completion: the ADR and roadmap are consistent with the spec; the owner is asked to
accept the ADR.

## Verification

`python3 -B -m unittest discover -s tests` (the suite reads no new files, so it
must be unchanged), `git diff --check`, `python3 install.py --check`, and a search of
the new documents for personal paths, identities, and `REPLACE_WITH_`.

## Risks and sensitive actions

- Increment A runs the other repositories' installers in scratch directories only.
  It creates a git repository there with a throwaway identity and uses no real
  address. No push, no commit, and no edit in either repository.
- `review-spec` and `review-adr` send the document to OpenAI; neither contains
  secrets or personal data.
- Otherwise none identified.

## Deferred work

- Writing any skill (roadmap candidates 2 to 7).
- A gap found in the template or the store, if any, as a request to its owner.

## Result

<!-- Complete this only after verification. Archive the plan according to
README.md, then reset this file to the empty template. -->
