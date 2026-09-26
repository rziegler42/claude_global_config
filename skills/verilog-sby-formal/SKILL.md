---
name: verilog-sby-formal
description: Use when writing, reviewing, or debugging Verilog-2001 formal proofs with SymbiYosys (`sby`): `.sby` tasks (bmc/prove/cover), harnesses, immediate assert/assume/cover, k-induction step failures, counterexamples from unreachable states, a cover that never reaches its goal (fill-then-drain, a completion, a return to idle), timeouts, or vacuous assumptions; also when asked to bump depth, or add an assume such as forcing a push or an opcode, to make a proof pass or a cover reach. Not for SystemVerilog assertions or plain simulation.
---

# Verilog + SymbiYosys formal verification

Use plain, Yosys-supported Verilog-2001. Do not introduce SystemVerilog syntax, SVA, interfaces, classes, or a second formal toolchain unless the repository explicitly authorizes them.

Read formal sources with `read_verilog -formal` in the `.sby` `[script]`. A plain `read_verilog` rejects the `assert`/`assume`/`cover` statements (`Can't resolve task name \assume`). It does parse `$past` and `$stable`, but they have formal meaning only in the formal flow. The `(* anyseq *)` and `(* anyconst *)` attributes also parse either way, and only the formal flow acts on them. Keep formal code under `` `ifdef FORMAL `` (with `-DFORMAL`) or in a separate harness file.

Task modes, a worked harness with its tested coupling, `.sby` templates (including a broken fixture), repository conventions, and sources are in `reference.md` beside this file; read it when writing a harness or task.

## Establish the proof boundary

Before writing a property, read the relevant RTL, existing formal harnesses and `.sby` tasks, and the contract or decision that defines the behavior. State the property as an observable claim: what is guaranteed, under which legitimate environment constraints, and at what boundary.

Keep a harness separate from production RTL by default. Code compiled under `FORMAL` is appropriate only when its ownership and synthesis exclusion are explicit. Exposing DUT state to a harness, whether by an added port or by checks inside the DUT under `FORMAL`, is such a change: apply the same rule, and prefer the check-inside-the-DUT option when a port would alter a module interface others depend on. Use the smallest DUT/harness that owns the behavior; do not begin diagnosis with a full-chip proof when a module or composition proof can isolate the failure.

## Model the environment faithfully

Use `(* anyseq *)` for values that may vary each cycle and `(* anyconst *)` only for a value that must remain constant across the trace. Constrain only real interface contracts: reset behavior, protocol legality, fairness when it is essential and documented, or explicitly chosen abstraction boundaries recorded under the written-source rule below.

`assume` constrains the world; `assert` constrains the DUT. Never make an assumption merely to select a convenient DUT state, instruction, occupancy, or transition for an entire trace. Such an assumption may remove legal counterexamples rather than prove a partition. If partitioning is needed, prove an exhaustive mapping of the original obligations and qualify each shard as `selector -> property` at the possible violation point.

An `assume` on an interface input (for example excluding an opcode or operand) needs a written source such as a spec clause or ADR. Until one exists, keep it out of the main task: put it in a separately named conditional task, leave the unconditional task unweakened, and report any result under it as conditional, never as an unconditional pass.

Guard `$past` with a past-valid register that has an explicit initial value, or with a reset/initial-state condition. Treat `$initstate` as an initialization tool, not as a substitute for an inductive invariant: induction starts from arbitrary reachable-looking states, not necessarily time zero. DUT registers without an `initial` value also start arbitrary; the time-zero reset assumption is what defines them after the first clock edge.

## Write proof-friendly properties

Favor small, independent claims over a monolithic restatement of the RTL:

- safety and bounds: occupancy/range, mutual exclusion, no response without a request;
- stability under stall: held request/address/data/control remain stable;
- exact-once lifecycle: admission, issue, completion, writeback, and retirement cannot duplicate or disappear;
- reset cleanup and cancellation;
- ordering and identity: a shadow transaction, token, or small counter follows the real lifecycle;
- data correctness: compare to an independently derived reference value or model, never a copy of the DUT expression.

For pipelines, queues, buses, and controllers, add ghost state that tracks the meaningful unit of work. A counter for outstanding work, a valid/id/data shadow, or an instruction packet carried through stages is often the missing inductive invariant. Check it at every ownership handoff. Prefer direct invariants that explain an induction failure over increasing the depth until it passes.

Use immediate properties in procedural Verilog, typically inside `always @(posedge clk)`. Place a clear comment beside each property naming the contract it protects. Keep covers separate from safety assertions when their setup or depth differs.

## Choose and record the task

Pick `bmc` (bounded counterexample search), `prove` (k-induction), or `cover` (reachability, vacuity detection); see `reference.md`. A passing bound is not an unbounded proof. Record mode, depth, timeout, engine, defines, top module, abstractions, and expected result (`expect pass` / `expect fail` in `[options]`) in the `.sby` file. If a solver fallback is needed, record why, its arguments, elapsed time, and outcome. Splitting tasks for faster feedback must not change the property, depth, or assumptions.

## Diagnose with evidence

On an assertion failure, inspect the generated trace and first identify whether it exposes a DUT bug, a harness/environment mistake, an initialization gap, or an incorrect property. Preserve the counterexample until the finding is resolved: `sby -f` deletes the old task directory, so copy the trace out before re-running.

On a cover that does not reach, cover one prerequisite earlier in the intended lifecycle and work forward; an unreached cover provides no success trace. Do not "fix" a failed cover by strengthening assumptions without independently justifying the resulting environment.

Treat `PASS`, `FAIL`, `TIMEOUT`, and `UNKNOWN` distinctly. A timeout or unknown is inconclusive, not a pass and not automatically a design defect. Record task identity, tool/engine, depth, timeout, elapsed time, and the scope actually closed.

## Demonstrate the proof is meaningful

Every important safety proof needs a complementary reachability witness: cover a useful end-to-end path, normally including a response/completion and return to an idle or reusable state; cover two or three transactions when throughput matters.

Keep at least one deliberately broken property or mutation fixture that fails with a retained counterexample, as a separate `.sby` task with `expect fail` and a define that enables the break (see `reference.md`). It validates that the task compiles the intended harness, the assumptions are not vacuous, and diagnostics are usable.

Formal complements dynamic verification: simulation for broad behavioral and timing evidence, formal for exhaustive local safety, ordering, and corner-state claims.

## Follow repository conventions

If the repository defines a property ledger, an established solver engine per mode, release or integration evidence requirements, or dynamic checks to rerun after formal RTL changes, follow them; see "Repository conventions" in `reference.md`. A green task without the repository's required records is not closure.

## Common mistakes

| Mistake | Fix |
|---|---|
| Raising depth to make an induction step pass | Add the missing invariant or reset/reachability anchor |
| `assume` used to pin the DUT to a convenient state | Assume only environment contracts; assert on the DUT |
| `$past` without an initialized past-valid register | `reg f_past_valid = 1'b0;` plus a time-zero reset assumption |
| Treating TIMEOUT/UNKNOWN as pass or as a bug | Report it as inconclusive with depth, engine, and elapsed time |
| Green safety proof with no cover | Add a reachability cover to rule out vacuity |
| Two competing non-blocking assignments to one counter | Compute the next value once (`case`) |
| Hierarchical reference (`d.count`) from a harness into a submodule | Yosys makes it an undriven free wire. Expose the state through a port, or check inside the DUT under `FORMAL`; start the harness file with `` `default_nettype none `` so any implicit declaration is a hard parse error, and treat "implicitly declared" / "no driver" warnings as errors |
