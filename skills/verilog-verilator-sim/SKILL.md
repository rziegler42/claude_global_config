---
name: verilog-verilator-sim
description: "Use when writing, reviewing, or debugging Verilator-based Verilog-2001 simulation drivers and testbenches: self-checking comparisons against a reference model, an intermittent or flaky simulation failure, a request to add a retry, skip, or timeout increase to make a flaky check pass, a golden-fixture mismatch, waveform/VCD debugging, blocking-vs-non-blocking races, or Verilator-specific warnings (UNOPTFLAT, INITIALDLY, X-elimination). Not for SystemVerilog assertions or `.sby`/formal proofs; see verilog-sby-formal for those."
---

# Verilog + Verilator simulation verification

Use plain, Yosys/Verilator-supported Verilog-2001 for the testbench and DUT alike. Verilator accepts several SystemVerilog-only system tasks (`$fatal`, `$error`) as an extension, but they are not part of Verilog-2001: print a single machine-parseable `TEST PASSED` / `TEST FAILED` line instead, and let the driver or CI wrapper set its exit code from that text rather than relying on `$fatal` for a nonzero exit. A worked example is in `reference.md`.

## Treat an intermittent failure as a real bug until proven otherwise

A Verilator simulation run, driven by the same binary with the same seed and the same inputs, is bit-exact. If a check fails on roughly 1 run in 20 and passes the rest, something *uncontrolled* is varying between runs: an unseeded `$random`/`random.seed()` call, the build's `--x-assign`/`--x-initial` policy, `--threads N > 1` evaluation-order sensitivity, or unseeded randomness in the reference model itself. Find and pin that variable before touching anything else.

1. Make the seed and every other run-to-run knob observable (printed at startup) and controllable (settable on the command line), across the stimulus, the reference model, and Verilator's own runtime randomization.
2. Replay one failing run with everything pinned. If it now fails every time, an "intermittent" bug has been reduced to an ordinary, reproducible one — debug it as such. If it is still intermittent with everything pinned, the bug is in the harness or build environment (an evaluation-order race, undefined behavior a sanitizer can catch), which is a real defect to find, not noise to average away.
3. Only once there is a reliable repro, enrich the mismatch report (dump a window of DUT and reference-model state around the failing cycle) and, if still needed, move to waveforms (`--trace`/`--trace-fst` + GTKWave), comparing the two traces rather than scrubbing one blindly.

**Never add a retry, skip marker, threshold increase, or timeout bump to a check that is asserting a correctness property (an occupancy bound, a comparison against a reference model, a mutual-exclusion condition) just because it is intermittent, without first disclosing that this may be masking a genuine bug and getting explicit confirmation.** Treat this exactly like a request to regenerate a golden fixture or to simplify a checker that disagrees with the DUT: investigate and report what was found before changing anything, rather than implementing the workaround and disclosing afterward.

| Excuse | Reality |
|---|---|
| "It's just flaking, add a retry" | Simulation is deterministic; intermittent means an unpinned variable, and that variable is itself worth finding |
| "We don't have time to root-cause today" | Pinning and printing the seed costs one line and turns "sometimes fails" into "reproduces every time" — that is the fast path, not the slow one |
| "A retry is harmless, it's not like editing the RTL or the checker" | A retry that hides a correctness-assertion failure ships the exact same bug a fixture rewrite or a bent checker would; the same discipline applies |

## Design the comparison, not just the stimulus

Compare the DUT against an independently derived reference model, never a restatement of the DUT's own expression — the same rule `verilog-sby-formal` states for `assert`. A model that recomputes the same fixed-width truncation or the same conditional the DUT uses can share the DUT's bug instead of catching it; prefer a differently-derived computation (for example, an arbitrary-precision counter truncated to width, rather than a second copy of the width-bounded increment-and-wrap logic).

Keep register-modeling always blocks non-blocking (`<=`), including a testbench's own reference-model registers — they represent synchronous state and must sample old values the way real flip-flops do. Reserve blocking assignments (`=`) for a single-writer stimulus or scoreboard-bookkeeping process, where there is no ordering hazard to protect against.

## Coverage is evidence, not proof

Line and toggle coverage confirm code ran and bits toggled; they say nothing about a cross-signal or exhaustive safety property (mutual exclusion, an occupancy bound across all reachable interleavings), and Verilator's line coverage has no condition/expression coverage, so a fully "covered" line can still hide an untested branch combination. Treat 100% structural coverage as regression-suite health, not as a substitute for a proof; use `verilog-sby-formal` for an exhaustive safety, ordering, or corner-state claim.

## Common mistakes

| Mistake | Fix |
|---|---|
| Reaching for `$fatal`/`$error` under a Verilog-2001 scope | Print a `TEST PASSED`/`TEST FAILED` sentinel; let the driver/CI wrapper set the exit code from it |
| Adding a retry/skip to a check asserting a correctness property because it's "just flaky" | Pin and print the seed, reproduce deterministically, disclose before working around it |
| Relying on Verilator's default zero-fill for uninitialized registers to "pass" | Run at least one regression with `--x-assign unique` (or equivalent) so a reset bug can't hide behind a lucky default |
| Reference model recomputes the DUT's own fixed-width or conditional logic | Derive the expected value independently (spec or behavioral model), not from the DUT's expression |
| Blocking assignment inside a clocked always block modeling real register state | Non-blocking (`<=`); blocking only for single-writer stimulus/bookkeeping |
| Regenerating a golden fixture to match new output without checking the new output is correct | Verify the new output against the spec first; only then update the fixture |
