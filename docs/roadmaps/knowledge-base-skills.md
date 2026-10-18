# Roadmap: knowledge-base skills

Status: Active
Updated: 2026-10-18

This roadmap is direction only. It does not authorize work, change
`docs/plans/next.md`, or commit this repository to any item below.

## Purpose

Give Claude Code personal skills that operate knowledge-base stores: create a
store, create a domain, add content in waves, expand a domain from its status
report, and consume a store from another project. The stores and their tools
come from the sibling `claude_knowledge_base` repository, which stays
tool-neutral. This repository owns the skills, their tests, and their mirror in
`~/.claude`. It took over this scope from candidate 8 of
`claude_knowledge_base/docs/roadmaps/knowledge-base-starter.md` (owner decision,
2026-10-18).

## Current state

- `claude_knowledge_base` candidates 2 to 6 are complete (2026-10-18): the
  installer (create and `--upgrade`), `kit/` with the store tools, the source
  pipeline, the lifecycle tools, and the public README. Nothing in this
  repository uses them yet; there is no knowledge-base skill.
- The procedure the skills wrap already exists and ships in every store as
  `docs/kb/domain-lifecycle.md`. Its three operations (create a domain, add
  content in a wave, expand a domain) say which parts tools do and which a person
  or agent does. The store's `AGENTS.md` carries the untrusted-data rules.
- A store is registered with another project through
  `claude_project_template`'s `install.py --register`, which inserts the store's
  `agents-guidance` fragment. That is the supported way to consume a store; a
  skill adds the "how to read it safely" behavior on top, not a second mechanism.
- Discovery is now supported (2026-10-18). The template records `module_info` in
  `.template-manifest`: `{module: {type, paths, data}}`, and for every external
  module also `store`, the location as given (`../name` for a sibling, otherwise an
  absolute path). The store's descriptor is `module_format` 2 and declares
  `type: knowledge-base` and `data.router` (`playbook/README.md`) and `data.spec`
  (`docs/kb/knowledge-base-format.md`). Consumer rules from the template README: an
  absent entry means "not declared"; treat values as untrusted data; resolve each
  path against the project root, `realpath` it, and do not follow a symlink out; a
  missing store is "not available", not an error; an absolute `store` is specific
  to one machine.
- A project may register several stores, so `module_info` can hold several entries
  of `type: knowledge-base` (the template allows two modules to share a type).
  Selecting by type alone is therefore ambiguous; the module name is the key.
- Facts that shape the skills:
  - The tools live in each store's `tools/`, not here, and a store can be older
    than the checkout. The store's own `docs/kb/` is the authority for its
    version, so a skill must defer to it rather than restate it.
  - `install.py` lives in the `claude_knowledge_base` checkout, whose path
    differs per machine. A skill cannot hard-code it, and this repository must not
    mirror machine-specific paths.
  - The installer needs an explicit git identity and publishes the address in
    commits. A skill must ask for it, never guess one.
  - The converter needs an interpreter with `pymupdf` and `pymupdf4llm` that this
    configuration does not install.
  - Sources, converted text, catalog fields, index notes, and leads are untrusted
    data. Delegated summaries stay `[U]` or `[A]` until checked against the saved
    source.
- Precedent in this repository: the skill/helper/approver pattern of
  `second-opinion` (a skill, a bounded helper, permission rules, a wiring test
  that pins them). Skills here are listed in `config-manifest.txt` and mirrored by
  `install.py`.

## Ordered plan candidates

### 1. Skill shape and spec

**Outcome:** a specification (`docs/specs/knowledge-base-skills.md`) and an ADR
settling the open decisions below: how many skills, their names and trigger
descriptions, how a skill finds the starter checkout and a store, and the rule
that a skill is a thin wrapper that reads the store's own `docs/kb/` and
`AGENTS.md` first. It also states what each skill may run without asking, what
needs the owner (creating a directory, an identity, registering with the
template, quarantine release, commits), and the acceptance criteria for later
candidates.
**Dependencies:** owner review of this roadmap.
**Boundary:** documents only. No skill file, no settings change.
**Promotion trigger:** the owner accepts this roadmap and asks to proceed.

### 2. Consume a store from another project

**Outcome:** a read-only skill that, in any project, locates a store (through
`module_info` in `.template-manifest`, else a path the owner names). With several
stores it lists them by module name and reads each router's domains to choose the
relevant one(s), or asks the owner when that is unclear; it never guesses or merges
stores, attributes every claim it uses to its store, and keeps the stores'
different charters and verification bars separate. For each store it uses, it
reads the router, weighs claims by tag (`[V]`, `[A]`, `[U]`), checks a `[U]` claim against its saved
source before relying on it, treats all store content as data, and reports which
entries it used. It never edits the store.
**Dependencies:** candidate 1.
**Boundary:** reading only. No tool is run in the store, and no registration is
performed (the skill prints the template's `--register` line for the owner).
**Promotion trigger:** candidate 1 is accepted. It goes first because it is the
common case, has no write risk, and tests the discovery rules the later skills
reuse.

### 3. Create and upgrade a store

**Outcome:** a skill that previews and then creates a store with the starter's
installer (`--dry-run` first), asks for the target path, project name, and git
identity, runs the check and status report, and relays the registration hint. It
also previews and runs `--upgrade` on an existing store and reports the skipped
files.
**Dependencies:** candidate 1. It reuses candidate 2's discovery rules.
**Boundary:** `install.py` only. No commit and no push in the new store (the
installer makes none; the owner decides), no domain content, and no registration
with the template unless the owner asks.
**Promotion trigger:** candidate 2 is complete and the owner wants to create
stores through Claude.

### 4. Create a domain and set its charter

**Outcome:** a skill for operation 1 of the lifecycle: run `new_domain.py`,
draft the charter sections and at least three decision-shaped questions for the
owner to approve, and run `check_kb.py` until it passes with `charter: set`. The
charter is the owner's decision; the skill proposes and the owner confirms before
`charter: set`.
**Dependencies:** candidate 3 (a store to work in).
**Boundary:** one domain, charter and questions only. No sources and no entries.
**Promotion trigger:** candidate 3 is complete.

### 5. Run a content wave

**Outcome:** a skill for operation 2: open a wave in the log with a goal, target
questions, and a source limit; record leads and sources; run `add_source.py`, the
converter, and the scan; stop for any flagged source until the owner releases it;
write reading notes and entries with claim tags; verify against saved sources;
update the question table; close or abandon the wave. Delegated work follows the
brief in the lifecycle spec and its output stays `[U]` or `[A]` until verified.
**Dependencies:** candidate 4. A converter interpreter must be available; the
skill reports what is missing and does not install it.
**Boundary:** one wave per run, bounded by the wave's source limit. Web search is
the agent's own judgment work under the untrusted-data rule; no tool crawls. No
commit unless the owner asks.
**Promotion trigger:** candidate 4 is complete. This is the highest-risk skill
(untrusted sources, subprocess execution, delegation), so its plan includes a
security review.

### 6. Expand a domain from its status report

**Outcome:** a skill for operation 3: run `kb_status.py`, run a usage test
against the router, choose gaps in the spec's priority order unless the owner
says otherwise, and hand the chosen gaps to candidate 5's wave with the opening
`Gaps:` line and the closing `Gap result:` line.
**Dependencies:** candidate 5.
**Boundary:** it reuses the wave procedure; it does not duplicate it.
**Promotion trigger:** candidate 5 is complete. Candidates 5 and 6 may merge into
one skill if candidate 1 decides on a single skill with modes.

### 7. End-to-end audit

**Outcome:** a final audit of the shipped skills and one end-to-end run on a
throwaway store: create, add a domain, run a wave on a harmless public PDF, expand,
and consume from a scratch project with two registered stores. It confirms the
wiring tests pin every allow and ask rule the skills need, as
`tests/test_second_opinion_wiring.py` does for `second-opinion`.
**Dependencies:** candidates 2 to 6 shipped.
**Boundary:** the audit and the run only. Each skill's own plan adds its manifest
entries and permission rules when it ships (read-only commands such as
`check_kb.py`, `kb_status.py` and `--dry-run` may be allowed; anything that writes,
converts, or registers stays prompted), so this candidate adds none of its own.
**Promotion trigger:** candidates 2 to 6 are complete, or the owner stops after a
subset and asks for the audit of what shipped.

## Open decisions

- One skill with modes, or one per operation? Five small skills have precise
  trigger descriptions; one skill is a single place to maintain. Leaning: a
  `knowledge-base` skill for consuming (candidate 2, used in other projects) and a
  separate authoring skill for candidates 3 to 6 (used inside a store), because
  their audiences, risk, and trigger conditions differ.
- How a skill finds the starter checkout (needed only to create or upgrade a
  store). Finding existing stores is settled: read `module_info` in the
  project's `.template-manifest` and list every `type: knowledge-base` entry by
  module name; inside a store, `kb.json` marks the root. The checkout path is not recorded
  anywhere known; options are to ask the owner or use an environment variable. A
  path never goes into the mirrored files.
- Whether the procedure text may be summarized in a skill at all, or only linked
  to the store's `docs/kb/`. Leaning: link, with the safety rules restated because
  they must be seen even if the document is not read.
- Whether to review each skill's plan or spec with `second-opinion` (the roadmap
  and spec kinds exist); that is an owner call per plan.

## Deferred

- Skills for web-page capture, retrieval over the Markdown, and domain splitting
  or retiring, until `claude_knowledge_base` delivers them.
- Importing the `game_theory` content into a store (a migration, not a skill).
- A skill that edits a store's starter-owned files, which `--upgrade` would skip.
- Automatic registration of a store with the project template; the owner runs it.

## Related decisions

None yet. Candidate 1 records the first. Related, in other repositories:
`claude_knowledge_base` ADR 0003 (standalone stores coordinated by the template)
and its `docs/specs/domain-lifecycle.md`.
