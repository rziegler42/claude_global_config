# 0008: Knowledge-base skills are thin wrappers that discover stores from the manifest

Status: Proposed
Date: 2026-10-18

## Context

`claude_knowledge_base` generates standalone stores with their own tools and procedure documents (`docs/kb/` in every
store). This repository is to own the personal skills that use and grow them (roadmap
[knowledge-base-skills](../roadmaps/knowledge-base-skills.md)). Three facts shape the skills. A store can be older than
the starter checkout, so the store's own documents describe its procedure. A store holds untrusted content, and its tools
are code that lives in its tree. And nothing records where the starter checkout is, while the template's
`.template-manifest` now records each registered store and its type, so more than one store can be present. The
specification is [knowledge-base-skills](../specs/knowledge-base-skills.md).

## Decision

- **Two skills.** `knowledge-base` consumes stores from any project and writes nothing. `knowledge-base-authoring`
  creates and upgrades stores, creates domains, runs content waves, and expands domains, with one reference file per
  operation. They are separate because their audience, risk, and trigger conditions differ.
- **Thin wrappers.** A skill links the store's own procedure documents instead of copying them, and restates only the
  safety rules. Store documents are untrusted data: they interpret the store but never widen what a skill may run. A
  skill runs only the tools and flags the specification lists, and any other flag needs the owner's approval.
- **Discovery from the manifest.** Inside a store, `kb.json` marks the root. Otherwise a skill reads `module_info` in
  `.template-manifest`, lists every `type: knowledge-base` entry by module name, and never selects by type alone. An
  owner-named path overrides discovery. `kb.json` is authoritative over the manifest's hints, and an unrecognized
  `kind` or `schema` stops the skill for that store.
- **No defaults for writes.** The authoring skill confirms the real path of its target with the owner before it first runs a
  store tool or writes, and never picks among several stores. Writes always prompt.
- **The starter checkout is asked for**, verified by `install.py`, `kit/kit.json` and `kit/files`, and never read from the
  environment, a store, or a mirrored file. No mirrored file carries a machine path or identity.

## Alternatives considered

- **Copy the procedure into the skills.** Rejected: the skills would drift from the starter and from older stores, and a
  store's version would no longer govern its own procedure.
- **Ship the skills inside the store or the starter.** Rejected: the starter and its stores stay tool-neutral (roadmap
  boundary), and a skill is personal configuration.
- **One skill with modes, or five skills.** One skill mixes a read-only consumer with a writing, subprocess-running
  author, which have different risk and trigger conditions. Five skills multiply trigger descriptions and shared rules
  that must stay identical. Two is the smallest split that separates the risk boundary.
- **Locate the starter by environment variable or a recorded path.** Rejected: the store does not record one, and a stored
  path is machine-specific state that must not be mirrored.
- **Let a store's documents supply tool flags.** Rejected: that lets untrusted content decide what runs.

## Consequences

- A change to the manifest or descriptor shape in either other repository can break discovery. The specification records the
  commits it was checked against, and a skill stops, naming the unexpected value, rather than guessing.
- A skill depends on the store's documents being readable and honest about the procedure. A hostile store can mislead the
  skill's reading of it, but cannot extend what it runs; the exposure is the store's own tools, which run only in a target
  the owner confirmed.
- The owner is asked for the starter path whenever a store is created or upgraded.
- Several stores in one project are handled by listing and asking, which costs a question when relevance is unclear.
- The wiring tests check skill text and permission rules, not behavior. Behavior is shown by the end-to-end run in candidate 7.

## Verification

Roadmap candidates 2 to 7 deliver the specification's acceptance criteria. This ADR stays `Proposed` until the owner
accepts it; the first skill's wiring test and the end-to-end run are the implementation evidence to record at acceptance.

## Related files and decisions

- Specification: [knowledge-base-skills](../specs/knowledge-base-skills.md); roadmap:
  [knowledge-base-skills](../roadmaps/knowledge-base-skills.md).
- In `claude_knowledge_base`: ADR 0003 (standalone stores coordinated by the template).
- This repository: [ADR 0001](0001-codex-reviews-with-a-prompt-only-read-boundary.md) (the same prompt-only boundary
  applies to untrusted content a skill reads) and [ADR 0004](0004-codex-approver-advice-only.md).
