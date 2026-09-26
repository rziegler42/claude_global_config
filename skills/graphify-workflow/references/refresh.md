# Graphify refresh procedure

Loaded from `SKILL.md`, section "Build or refresh". Follow it exactly when a
build or refresh has already been judged worthwhile.

1. Run `claude-workflow graph-prepare` (`--deep` only when requested). Never run
   it while a refresh is in progress (`graph-doctor` reports a `prepared_*`
   state): it would overwrite the manifest and delete chunks that workers
   already wrote. The helper refuses; resume, finalize, or abort instead.
2. Read `graphify-out/.graphify_chunks.json` once. It contains the complete
   contract.
3. If there are chunks, dispatch every chunk to the `graphify-semantic` agent,
   in parallel batches of at most four concurrent workers unless the user asks
   for more. Pass only its file list, exact output path, deep flag, per-file
   size and SHA-256 records, and manifest contract. The worker must read every
   assigned file in full, using paged reads through EOF when necessary, and
   must not write a provisional chunk.
4. Accept a worker handoff only when it returns exactly
   `COMPLETE <assigned-path> coverage <N>/<N>` with the expected path and
   assigned-file count. An output file without that completion report remains
   incomplete and must not be validated or finalized. If a worker stops at its
   turn limit or returns `INCOMPLETE`, resume that same worker with: `Continue
   the existing chunk assignment. Determine which assigned files have not
   reached EOF, read all remaining content using paged reads, and do not write
   or revise the chunk until every assigned file is complete. Then write the
   assigned output and return the required COMPLETE report.` Never instruct a
   worker to skip, abbreviate, assume, or avoid re-reading source content.
5. The parent validates each completed path with exactly
   `claude-workflow graph-validate-chunk <assigned-path>`. If it fails, send the
   exact failure to the original worker for one focused `Edit` of that same
   path, then validate once more. A denied write, missing output, or second
   validation failure stops the refresh without finalizing. Workers have no
   shell access and may never use a script or Bash command to write a chunk.
   Treat validator-reported counts as authoritative; ignore worker hand tallies.
   Coverage validation proves exact prepared sources were acknowledged at their
   prepared hashes, not that the semantic interpretation is complete.
6. After every worker has returned a completion report and every chunk has
   validated, run `claude-workflow graph-finalize` directly. Finalization must
   refuse any missing, stale, structurally invalid, or coverage-incomplete
   chunk.
7. Report graph size and before/after delta, failed chunks, visualization mode,
   and commands actually run. `graph.html` is current only when the finalizer
   reports a generated visualization; otherwise consult `GRAPH_REPORT.md` and
   `.claude_graph_visualization.json`, never a prior viewer.

If a prepared refresh is abandoned before any assigned semantic chunk exists,
cancel it only with `claude-workflow graph-abort --confirm`. It removes the
prepared marker and its manifest, restoring ordinary graph status. It refuses
to discard a refresh once any assigned chunk exists; then resume or finalize
instead. If `graph-doctor` reports `prepared_manifest_missing` (a prepare that
failed early), `graph-abort --confirm` clears the marker, since no chunk can
exist without a manifest; re-run `graph-prepare` if the refresh is still
wanted. Never remove refresh state or manifests manually.

Do not independently rewrite worker output, reuse a failed old chunk, or ask
for chunk JSON in chat. Parent-side validation is required; it is not an
independent semantic rewrite.
