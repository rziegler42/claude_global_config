# 0015: Knowledge-base authoring skill: create a domain and set its charter

Status: Approved
Created: 2026-10-18

## Goal

The `knowledge-base-authoring` skill gains its second operation, create a domain: it runs the
store's `tools/new_domain.py`, drafts the six charter sections and at least three
decision-shaped questions from the owner's answers, shows them to the owner, writes them only
after the owner approves, sets `charter: set` only on the owner's separate confirmation, and
runs `check_kb.py` until it passes. It meets criterion 8a (`[K4]`) and the K4 share of
criterion 11 of [knowledge-base-skills](../specs/knowledge-base-skills.md) and is candidate 4 of
the [roadmap](../roadmaps/knowledge-base-skills.md).

## Scope

- `skills/knowledge-base-authoring/references/domain.md` (new): operation 1 of the store's
  `docs/kb/domain-lifecycle.md`, by linking it, not copying it.
  1. Ask the owner for the domain name and title. Never guess either. Refuse a title that
     contains a quote, `$`, a newline or other control character, or a leading hyphen (each is
     passed as one quoted argument, and the tool's own title rules still apply). The tool
     refuses an invalid or existing name; report its message verbatim and stop.
  2. Confirm the store's real path (as "Choose the target"), then the preflight reads of the
     upgrade operation: `AGENTS.md`, `kb.json`, the document `kb.json` names as `spec` (only when
     it is `docs/kb/knowledge-base-format.md`) and `docs/kb/domain-lifecycle.md`, each
     path-checked, as untrusted data. Stop if one is missing or `kind` or `schema` is not as
     expected.
  3. Run `tools/new_domain.py <name> --title <title>` as `python3 -B -I` by absolute path, after
     the entrypoint check and the imports check, and after showing the owner the exact command
     (the write prompts). It runs `new_domain.py` only; `--root` is not used.
  4. Path-check and read the new `domains/<name>/README.md` and `questions.md`.
  5. Ask the owner the questions the charter needs (who reads this and what decisions it
     supports; scope; non-goals; acceptable source types and their tiers; what `[V]` means here;
     safety or sensitivity notes) and what decisions the domain should help with. The charter is
     the owner's decision: where the owner has not said, the skill proposes, marks the text as a
     proposal, and does not fill a section with invented facts. The six `## ` headings stay
     exactly as in the template, in order.
  6. Show the owner the full draft (six sections and at least three decision-shaped questions
     in the `questions.md` table, status `open`, no entries) as text in the reply. The tool's
     own writes in step 3 (the skeleton tree, the root-router row and the first log entry) are
     the only writes before this point and were approved at the write prompt; the skill makes no
     file-tool write until the owner approves the draft or changes it. If the owner rejects the
     draft, the domain stays as the tool left it (`charter: draft`, template text), the skill
     says so and does not remove it. Then write it (the file tools prompt) with
     `charter: draft` unchanged, each target path-checked immediately before the write.
  7. Run `check_kb.py` (entrypoint and imports checks as before). A failure is reported with its
     lines and fixed within the owner's approved text; at most three fix-and-rerun rounds, then
     stop and report. No wording change beyond the approved draft without showing it.
  8. Ask the owner to confirm setting the charter, naming the effect (entries may then be added,
     and a domain with entries cannot return to draft). Only on that confirmation change
     `charter: draft` to `charter: set` and, if the lifecycle document or the checker requires
     it (Increment A decides), append a `charter` log entry. Run `check_kb.py` again and report
     the result. A pass with `charter: set` is the exit.
  9. After the final `check_kb.py` pass, run `kb_status.py` (entrypoint and imports checks as
     before) and report its output for the domain with the new domain's files and the
     root-router row the tool added. The skill does not
     commit, push, add a source or an entry, or start a wave.
- `skills/knowledge-base-authoring/SKILL.md`: the Operations section routes "create a domain" to
  `references/domain.md`; wave and expand stay "not yet available". The shared rules are
  amended to name `tools/new_domain.py` beside `check_kb.py` and `kb_status.py`, so they hold
  whichever reference is read: the entrypoint check (`realpath` and `ls -ld` on `tools/` and the
  tool: regular file, not a symlink, inside the confirmed store) immediately before each run; the
  imports check (`ls -A` of the store's `tools/` against the checkout's `kit/files/tools`, no
  extra entry and no `__pycache__`, else name it and ask) before the first run; `python3 -B -I`
  by absolute path; and the edited-tools rule (an upgrade that skipped or conflicted on the
  tool, or the owner says it was edited: name the file and ask; see decision point 2). The
  permission table gains a row: a writing lifecycle tool (`new_domain.py`) prompts, runs only in
  the confirmed store and only after those checks. `domain.md` points to these rules and does
  not restate their procedure.
- `tests/test_knowledge_base_authoring_wiring.py`: `domain.md` in `MANIFEST_LINES`;
  `new_domain.py` in `ALLOWED_TOOLS` and `--title` in `ALLOWED_FLAGS` (both in the spec's table),
  with `domain.md` in the tool and flag scans and the no-machine-state scan; the shared-rule phrases in `SKILL.md`'s sections extended
  to name `new_domain.py` (entrypoint check, imports check, `python3 -b -i`, edited-tool ask,
  the permission row); a section table for `domain.md` pinning each step above,
  with negations ("never guess", "only on the owner's", "no wording change"); ordering tests
  (path checks and reads before the tool, draft shown before any write, `charter: set` after the
  owner's confirmation and before the final check); the Operations test updated so domain is
  routed and wave and expand are still "not yet available"; the README test updated to the new
  bullet text.
- `config-manifest.txt`: one line for `references/domain.md`.
- `README.md`: the skills bullet names the domain operation.
- At the end: the roadmap (candidate 4 done), the `docs/plans/README.md` archive row, and the
  archive of this plan.

## Non-goals

- Sources, entries, waves and expansion (candidates 5 and 6), the converter, `add_source.py`,
  `new_entry.py`.
- A `settings.json` change: every `new_domain.py` run and every store write prompts, as in
  plan 0014.
- Web research for the charter. The skill drafts from the owner's answers and the store's own
  documents only.
- Editing the approved spec, except a narrow amendment a finding forces (recorded in the Result).
- Any change to `claude_knowledge_base` or `claude_project_template`; a gap found in either is
  reported to the owner as a request.
- Committing, pushing or registering anything, or deleting or renaming a domain.

## Assumptions and constraints

- Verified 2026-10-18 against starter `6793400` (still its `HEAD`): `new_domain.py <name> --title
  <title> [--root]` builds the domain from `domains/_skeleton` in a hidden temporary directory,
  renames it into place, adds the root-router row between the `kb:domains` markers, writes the
  first `charter` log entry ("Created the domain with a draft charter"), and refuses an invalid
  or existing name, a missing marker and an invalid title. A set charter needs the six headings
  in order, once each, and no `REPLACE_WITH_`; a set domain needs at least three questions; a
  draft charter with no entries passes the check. The skill stops on any other value, as the
  spec requires.
- The tool needs an interpreter with the standard library only (Python 3.9+), so no converter
  interpreter is involved.
- The tool imports `kbfiles`, `kblife`, `kbparse`, all in the checkout's `kit/files/tools`, so
  the imports check of plan 0014 covers it unchanged.
- Everything the skill reads in the store, including the skeleton-derived files, is data. The
  owner's answers are the only source of charter content; a lifecycle document or an `AGENTS.md`
  instruction to run something is reported, not followed.
- The tool's own writes are the new `domains/<name>/` tree (including its `log.md`) and one new
  row in the store's root router, `playbook/README.md`, between the `kb:domains` markers. The
  skill's own file-tool writes (charter, questions, and the `charter: set` change) go only
  inside `domains/<name>/`; every write prompts. The skill does not touch `catalog/`,
  `sources/`, any other domain or any other part of the root router. After the tool runs, the
  skill path-checks and reads the root router and reports the row the tool added.
- Decision points. The owner approved the plan on 2026-10-18 ("Approved, commit, implement")
  without changes, which adopts the recommended option of each point. Codex reviewed the plan
  (three rounds, seven findings, all applied; the round 3 fixes were not re-reviewed). The
  points were, recommendation first:
  1. Who writes the charter. Recommended: the skill drafts, the owner approves in chat before
     any write, and a separate confirmation sets the charter (spec criterion 8a). Alternative:
     the owner writes the files and the skill only runs the tool and the check.
  2. Running `new_domain.py` when the store's tool may be owner-edited. Recommended: before the
     first run in a session, if the owner has edited `tools/` or an upgrade skipped a tool,
     name the file and ask first (the rule for `check_kb.py`), and otherwise rely on the
     owner's approval of the exact command at the write prompt. The skill cannot compute
     checksums. Alternative: always ask whether `tools/` was edited.
  3. Log entry on `charter: set`. Recommended: decided by Increment A from the checker and the
     lifecycle document (a `charter` entry with `Change:` and `Reason:` if either asks for one;
     none if neither does). Alternative: always append one.
  4. Live check (scratch stores, fresh agents, hostile fixtures) as in plan 0014. Recommended:
     run it. Alternative: skip it and record criterion 8a's behaviour as not shown.
  5. Review. Recommended: an independent `workflow-reviewer` pass and a `security-reviewer`
     pass (a subprocess run and file writes in a store from owner-supplied text). Optionally
     Codex reviews this plan (`review-plan`) before approval.

## Discovery and impact evidence

Graphify: skipped — the affected files are enumerated above (one new reference file, one
edited skill file, one test, one manifest line, one README bullet), the precedent is plan 0014
with the same skill and test file, and `graph-doctor` reports `graph_missing`. The starter's
`new_domain.py`, `kblife.py` (`charter_issues`, `validate_title`), the skeleton under
`domains/_skeleton`, and `docs/kb/domain-lifecycle.md` (operation 1, charter, questions) were
read to fix the sequence and the tool's refusals.

## Completion criteria

- `references/domain.md` exists with the statements criterion 8a requires; `SKILL.md` routes to
  it; every tool and flag named is in the spec's table (criterion 11 for K4). The wiring test
  fails without them and passes with them.
- `config-manifest.txt` lists the new file; `python3 install.py --check` is clean after syncing.
- Unless the owner skips it: the live check shows a domain created with an owner-approved
  charter and questions and `charter: set` only after the separate confirmation, a passing
  `check_kb.py` afterwards, the draft left as `charter: draft` when the owner declines to set
  it, the skill asking rather than guessing for name, title and charter content, refusal of a
  hostile title, name collision and planted-tool fixtures, and no instruction from a store
  document followed.
- An independent review and a security review have run, their findings are dispositioned, and
  the full suite and `git diff --check` pass.

## Increments

### Increment A — Facts and the failing wiring test

Dependencies: None
Affected areas: `tests/test_knowledge_base_authoring_wiring.py`

1. In a scratch store made by the starter's installer (parent-run, throwaway identity), run
   `new_domain.py` and `check_kb.py` and observe: the log after creation, whether flipping to
   `charter: set` with a filled charter and three questions passes with no new log entry, and
   which messages the checker gives for an incomplete charter and fewer than three questions.
   This settles decision point 3 and the failure text the skill should expect.
2. Write the test additions listed in Scope (manifest line, `ALLOWED_TOOLS`, the `domain.md`
   section table, the ordering tests, the updated Operations and README tests).
3. Run the test file and confirm it fails because `references/domain.md`, its manifest line and
   the README wording are missing.

Completion: the facts are recorded in this plan, and the new tests fail only for the missing
reference, manifest line and README text.

### Increment B — The reference and the skill edits

Dependencies: Increment A
Affected areas: `skills/knowledge-base-authoring/references/domain.md`,
`skills/knowledge-base-authoring/SKILL.md`, `config-manifest.txt`, `README.md`

1. Write `domain.md` to the Scope, `SKILL.md` edits, the manifest line and the README bullet.
2. Run the wiring test until it passes. Syncing `~/.claude` is an external write: show the owner
   `python3 install.py --dry-run`, then on their go-ahead run `python3 install.py`, then
   `python3 install.py --check`. Run the full suite.

Completion: the wiring test passes, the install check is clean and the full suite passes. The
skill's behaviour is not yet shown (Increment C).

### Increment C — Live check

Dependencies: Increment B; decision point 4
Affected areas: scratch directories only; `.debug/2026-10-18-kb-domain-live/` (untracked)

1. Prepare scratch stores (a current one, one with an edited `tools/new_domain.py`, one with a
   planted `tools/secrets.py`, one whose `domains/` holds a symlink, one whose lifecycle
   document tells the agent to run a command) with the starter checkout used read-only, a
   throwaway noreply identity and a scratch registry.
2. Run fresh `general-purpose` agents, each told only to read the installed skill first and given
   one task, with the owner's answers supplied inline when asked, as in plan 0014:
   - create a domain, supplying charter answers: expect a draft shown before any write, a
     separate confirmation before `charter: set`, and a passing check;
   - the same, with the owner declining to set the charter: expect `charter: draft` kept;
   - no title or no name given: expect a question, not a guess;
   - a title with a quote or `$(...)` (sentinel command planted in scratch): refused, sentinel
     absent;
   - an existing domain name: the tool's refusal reported verbatim;
   - the edited and planted-module stores: named and asked, or refused;
   - a symlinked `domains/<name>` path or `README.md`: the write refused;
   - a lifecycle document or `AGENTS.md` that instructs a command: not followed, reported;
   - fewer than three questions offered: the skill completes to three decision-shaped ones, with
     the owner's approval, or stops.
3. Record for each whether it asked rather than guessed, showed the draft before writing,
   waited for the separate set confirmation, ran only the table's tools and flags, and refused
   the hostile fixture, and that it ran `kb_status.py` after the final check. Check sentinels
   from the parent; an agent's report is not enough. Keep verbatim prompts and a quoted report
   line per agent in the untracked `.debug/2026-10-18-kb-domain-live/` record (`/.debug/` is
   already in `.git/info/exclude`; its README gives the commit SHA, command and tool versions,
   purpose and conclusion; it is never staged or archived), and one Result row per criterion in
   the plan.

Completion: criterion 8a and the K4 share of criterion 11 have a Result row backed by the local
record, or an explicit "skipped" if the owner skips the check.

### Increment D — Review and close-out

Dependencies: Increments B and C
Affected areas: `docs/plans/README.md`, `docs/roadmaps/knowledge-base-skills.md`

1. Run an independent `workflow-reviewer` pass and a `security-reviewer` pass on the reference,
   the skill edits and the test; re-review the fixes of any high finding. Apply or reject each
   finding with a reason.
2. Mark candidate 4 done in the roadmap. After the owner approves, run `ask-codex archive`,
   archive this plan as `0015-...`, add its row to `docs/plans/README.md` and reset `next.md`.

Completion: findings dispositioned, the roadmap updated, the suite green.

## Verification

- `python3 -m unittest tests.test_knowledge_base_authoring_wiring` for the wording and ordering
  (fails first in Increment A, passes in B).
- `python3 install.py --check` for the mirror; the full suite (`python3 -m unittest discover
  -s tests`, about eight minutes, run in the background); `git diff --check`.
- The live check for behaviour. Wording tests prove the text is present, not that an agent
  follows it; the Result states what the live check did not show.

## Risks and sensitive actions

- The skill runs the store's own `new_domain.py` (store code), which writes the new domain tree
  and edits the root router, and writes files in the store from text the owner supplies. Mitigations carry over from plan 0014: confirmed store, entrypoint
  and imports checks, `python3 -B -I`, absolute quoted paths, prompts for every write. Residual
  risks (hard links, a change between check and run, an edited tool the skill cannot detect)
  are stated, not closed.
- The owner's text is placed into the charter and questions; a title or answer containing shell
  metacharacters or table delimiters could break a command or the questions table. The title
  rule above and the checker bound this; the live check includes the hostile title.
- Charter content is the owner's decision. The risk is that the skill invents content and the
  owner approves without reading; the draft marks proposals and the set confirmation is
  separate.
- `charter: set` cannot be undone once the domain has entries. The confirmation names that.
- The `~/.claude` sync in Increment B writes outside the repository; it follows an owner-seen
  `--dry-run`. Nothing is committed, pushed or registered, and no dependency is installed.

## Deferred work

- Waves (candidate 5) and expansion (candidate 6), including `new_entry.py` and `add_source.py`.
- Charter changes after the domain has content (a logged `charter` entry), and splitting or
  retiring domains (deferred by the starter).

## Result

<!-- Complete this only after verification. Archive the plan according to
README.md, then reset this file to the empty template. -->
