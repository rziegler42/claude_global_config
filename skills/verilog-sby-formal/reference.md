# verilog-sby-formal reference

Supporting material for `SKILL.md`: task modes, a worked harness with its tested coupling, `.sby` templates (including a deliberately broken fixture), repository conventions, and sources.

## Task modes

- `mode bmc`: bounded, from-reset evidence and concrete counterexample search. A passing bound is not an unbounded proof.
- `mode prove`: k-induction safety claims. It includes a bounded base check and an arbitrary-state induction step. An induction failure usually calls for a missing invariant, reset/reachability anchor, or an over-broad assertion, not a blind depth increase.
- `mode cover`: reachability and vacuity detection: reset exit, useful transaction completion, return to idle, back-to-back work, and important exceptional paths.

For tiny control-only Boolean safety problems, a qualified SAT/ABC/PDR task may be preferable. For bit-vector BMC use a bounded SMT engine; for induction use an induction-capable engine. For multiple clocks, add `multiclock on` to `[options]`.

## Minimal Verilog-2001 patterns

Harness for a DUT that is the *responder*: `i_req`/`i_addr`/`i_data` are inputs (assumed), `o_ready`/`o_ack` are outputs (asserted). If the DUT is the requester, swap `assume` and `assert` in the stall block.

```verilog
`ifdef FORMAL
    // Anchor time zero: $past is meaningless on the first cycle, and the
    // design must start in reset. The initial value is required; without it
    // the solver may choose f_past_valid = 1 at time zero.
    reg f_past_valid = 1'b0;
    always @(posedge i_clk)
        f_past_valid <= 1'b1;
    always @(*)
        if (!f_past_valid)
            assume(i_reset);

    // Ghost counter: requests accepted but not yet acknowledged.
    localparam MAX_OUTSTANDING = 8;
    reg [3:0] f_outstanding = 4'd0;
    wire f_accept = i_req && o_ready;

    // Reset has priority. A simultaneous accept and ack cancels out, so the
    // next value is computed once instead of by two competing assignments.
    always @(posedge i_clk)
        if (i_reset)
            f_outstanding <= 4'd0;
        else
            case ({f_accept, o_ack})
            2'b10:   f_outstanding <= f_outstanding + 4'd1;
            2'b01:   f_outstanding <= f_outstanding - 4'd1;
            default: f_outstanding <= f_outstanding;
            endcase

    always @(posedge i_clk)
        if (!i_reset) begin
            // No acknowledgement for work that was never accepted.
            if (o_ack)
                assert(f_outstanding != 0);
            // Occupancy bound; the DUT must stop accepting when full.
            assert(f_outstanding <= MAX_OUTSTANDING);
            if (f_outstanding == MAX_OUTSTANDING)
                assert(!o_ready);
        end

    // Environment contract: a stalled request is held until it is accepted
    // or reset intervenes.
    always @(posedge i_clk)
        if (f_past_valid && !$past(i_reset)
                && $past(i_req && !o_ready)) begin
            assume(i_req);
            assume($stable(i_addr));
            assume($stable(i_data));
        end

    // Reachability witness: work is acknowledged, so the asserts above are
    // not passing on a design that never responds.
    always @(posedge i_clk)
        if (f_past_valid && !i_reset)
            cover(o_ack);
`endif
```

Keep arithmetic widths, simultaneous request/response semantics, reset priority, and wrap behavior explicit in real properties; the pattern is a starting point, not a complete protocol proof.

For `mode prove`, the ghost counter must also be tied to the DUT's own state, plus any relation between its other registers (for example `o_ack` implies the DUT's occupancy is non-zero). Otherwise induction starts from an arbitrary DUT state unrelated to the ghost and fails on the `o_ack` assertion. `mode bmc` from reset passes without the coupling.

Reach that state through a port (for example an `o_count` output wired to a harness wire) or write the invariant inside the DUT under `` `ifdef FORMAL ``. Do not write a hierarchical reference such as `d.count` from the harness: Yosys does not resolve it to the instance's register. It warns `Identifier ... is implicitly declared` and `Wire ... is used but has no driver`, then treats the name as a free wire the solver can set to anything, so the invariant fails on impossible traces. Treat those two warnings as errors.

Tested coupling for the harness above. The DUT gains `output [3:0] o_count` driven by its internal counter; the harness declares `wire [3:0] f_count;`, connects `.o_count(f_count)`, and adds:

```verilog
`ifdef FORMAL
    // Tie the ghost counter to the DUT's real state so induction cannot
    // start from an unrelated arbitrary DUT state.
    always @(posedge i_clk)
        if (f_past_valid) begin
            assert(f_count == f_outstanding);
            // DUT-specific relation between its own registers: an
            // acknowledgement implies something is outstanding.
            if (o_ack)
                assert(f_count != 0);
        end
`endif
```

With this added, `bmc`, `prove` (base and induction), and `cover` all pass on a toy responder.

Put `` `default_nettype none `` on the first line of the harness file so a misspelled name or a hierarchical reference is a hard parse error (``Identifier ... is implicitly declared and `default_nettype is set to none``) instead of a warning. Check that the harness declares every wire it uses, including ones connected to instance ports.

## Minimal `.sby` task

```
[tasks]
bmc
prove
cover

[options]
bmc: mode bmc
bmc: depth 30
prove: mode prove
prove: depth 20
cover: mode cover
cover: depth 40
timeout 300

[engines]
smtbmc yices

[script]
read_verilog -formal -DFORMAL dut.v harness.v
prep -top harness

[files]
dut.v
harness.v
```

Run with `sby -f dut.sby prove`. `-f` deletes the previous task directory, including any counterexample in it: copy a trace you still need out first (or give the run its own directory with `-d`) before re-running. Traces are under the task directory `<file>_<task>/engine_0/`: `trace.vcd` for a `bmc` counterexample, `trace_induct.vcd` for a failed induction step, and `trace0.vcd` for a reached cover (with matching `*_tb.v` and `.yw` files). Use the repository's established engine in place of `yices` and record depth, timeout, and expected result per task.

To prove a parameterized module across more than one configuration, add `-chparam NAME value` to the `hierarchy` line (`hierarchy -check -top dut -chparam WIDTH 8`) and give each configuration its own task with a `script:`-tagged override, rather than one task that only exercises the default parameter values.

## Deliberately broken fixture

A separate task that must fail proves the harness really checks something. Guard a false assertion with a define, and give that task `expect fail` and the define:

```verilog
`ifdef BREAK
    always @(posedge i_clk)
        if (f_past_valid && !i_reset)
            assert(f_outstanding == 0);   // false once anything is accepted
`endif
```

```
[tasks]
bmc
broken

[options]
bmc: mode bmc
bmc: depth 30
broken: mode bmc
broken: depth 30
broken: expect fail
timeout 300

[engines]
smtbmc yices

[script]
bmc: read_verilog -formal -DFORMAL dut.v harness.v
broken: read_verilog -formal -DFORMAL -DBREAK dut.v harness.v
prep -top harness

[files]
dut.v
harness.v
```

`sby -f dut.sby bmc broken` reports `DONE (PASS, rc=0)` for `bmc` and `DONE (FAIL, rc=0)` for `broken`: the failure is the expected outcome, and the counterexample is written to `dut_broken/engine_0/trace.vcd`. Add `expect pass` (the default) or `expect fail` to any task to record its expected result.

## Repository conventions

When the repository defines any of the following, follow it; otherwise skip the item.

- A property ledger or manifest: give each changed behavior an entry recording owner, assumptions, task, proof style, scope, and result. A green task without that entry is not closure.
- An established solver engine per mode: use it instead of running a solver matrix. Resource budgets apply across parallel SBY tasks, engines, and solver threads; do not maximize all three.
- Release or integration evidence requirements: keep them unchanged when splitting fast focused tasks from long from-reset BMC/cover tasks.
- Formal changes to RTL: rerun the affected dynamic checks on the final RTL before reporting closure.

## Sources

Apply these ideas as engineering guidance, adapted to the repository's actual contracts:

- [SymbiYosys: quickstart guide](https://symbiyosys.readthedocs.io/en/latest/quickstart.html) — the tool's own reference: task tags including `:default`, `-noverific` to force the plain (non-SystemVerilog) Verilog frontend, and `hierarchy -chparam` for parameterized configurations. Prefer it over this skill for `.sby` syntax questions not covered here.
- [YosysHQ: riscv-formal](https://github.com/YosysHQ/riscv-formal) — an instruction-set proof framework: a wrapper module isolates instruction semantics from microarchitecture behind a stable retirement interface (RVFI), and one templated check per instruction is generated from a shared script rather than hand-written per opcode. It also favors immediate assertions/assumptions throughout for tool compatibility, matching this skill's own preference. Adapt the isolation pattern for any instruction-set core; the RISC-V-specific interface itself does not apply outside RISC-V.
- [ZipCPU: formal verification plan](https://zipcpu.com/formal/2020/07/21/formal-plan.html) — design-owned invariants, outstanding-work counters, and induction.
- [ZipCPU: formal induction exercise](https://zipcpu.com/blog/2018/03/10/induction-exercise.html) — base versus induction and why initialization alone does not prove arbitrary states.
- [ZipCPU: SBY Makefile workflow](https://zipcpu.com/zipcpu/2018/12/20/sby-makefile.html) — separate safety and cover tasks, automation, and avoiding vacuity.
- [ZipCPU: formal and simulation](https://zipcpu.com/formal/2019/10/05/formal-enough.html) — covers for completion, reuse, and throughput alongside simulation.
- [ksriram.dev: formal verification, part 2](https://ksriram.dev/posts/formal-2/) — separating an independent spec expression from the DUT expression it checks, and using implication (`assert(sel -> property)`) to scope a property to one mode without a separate block per mode.
- [YosysHQ: solving Sudoku with SymbiYosys](https://blog.yosyshq.com/p/solving-sudoku-with-sby/) — `cover` as a satisfiability witness for a constraint set: an unreached cover on a state the assumptions should permit exposes a contradiction in the assumptions, not just an unreached DUT path.
- [ksriram.dev: formal verification, part 1](https://ksriram.dev/posts/formal-1/) and [autonomousvision.io: formal verification with SymbiYosys](https://www.autonomousvision.io/blog/formal-verification-symbiyosys) — further worked introductions to the same `ifdef FORMAL`/assume/assert/cover workflow, useful as a second explanation rather than new technique.
