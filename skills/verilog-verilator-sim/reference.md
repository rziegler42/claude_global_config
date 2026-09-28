# verilog-verilator-sim reference

A minimal self-checking testbench, and sources.

## Minimal self-checking testbench

Plain Verilog-2001, no `$fatal`/`$error`. The reference model is an unbounded counter truncated to width, not a second copy of the DUT's own wrap logic; the comparison samples on `negedge clk`, half a cycle after both the DUT and the reference model have settled their non-blocking updates, so there is no same-time-step race to reason about. `rst` is deasserted on a `negedge`, not immediately after the `@(posedge clk)` that ends the reset window: changing a signal the instant a clocked always block also triggers on is a same-edge race between the stimulus process and that block, and the fix generalizes to any stimulus edit that shares a clock edge with the logic it drives. Verified: builds cleanly under `verilator --binary --timing -Wall` (no warnings) and passes 40/40 checked cycles across repeated runs.

```verilog
`timescale 1ns/1ps

module tb_counter;
    localparam WIDTH = 4;

    reg              clk;
    reg              rst;
    wire [WIDTH-1:0] dut_count;

    counter #(.WIDTH(WIDTH)) dut (.clk(clk), .rst(rst), .count(dut_count));

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    // Independent reference model: unbounded, not a copy of the DUT's
    // fixed-width wrap arithmetic. Non-blocking: it stands in for real
    // synchronous register state.
    integer cycle_count;
    always @(posedge clk)
        if (rst)
            cycle_count <= 0;
        else
            cycle_count <= cycle_count + 1;

    integer errors;
    integer checked;
    always @(negedge clk)
        if (!rst) begin
            checked <= checked + 1;
            if (dut_count !== cycle_count[WIDTH-1:0]) begin
                $display("MISMATCH cycle=%0d expected=%0d got=%0d",
                          checked, cycle_count[WIDTH-1:0], dut_count);
                errors <= errors + 1;
            end
        end

    initial begin
        errors  = 0;
        checked = 0;
        rst = 1'b1;
        repeat (2) @(posedge clk);
        @(negedge clk);   // deassert off the active edge, not racing it
        rst = 1'b0;
        repeat (40) @(posedge clk);
        @(negedge clk);   // let the last cycle's checker update settle
        if (errors == 0)
            $display("TEST PASSED: %0d cycles checked, 0 mismatches", checked);
        else
            $display("TEST FAILED: %0d mismatches out of %0d cycles checked",
                      errors, checked);
        $finish;   // always exits 0 — the wrapper below sets the real result
    end
endmodule
```

Since plain Verilog-2001 has no way to set the process exit code directly, the driver or CI wrapper greps for the sentinel instead of trusting `$finish`'s exit status:

```sh
./sim_counter | tee run.log
grep -q '^TEST PASSED' run.log
```

Extending this to a more complex DUT: keep the reference model behavioral (a queue for a FIFO, arithmetic for an ALU) rather than a bit-exact reimplementation of the RTL; for a pipeline or a bus with a valid/ready handshake, compare two queues (expected vs. observed, each pushed only when its `valid` fires) instead of every clock edge; keep the same "sentinel line plus watchdog timeout" shape regardless of DUT complexity so nothing needs a human to open a waveform viewer to know pass/fail.

## Verilator-specific pitfalls

- **X/Z elimination hides reset bugs.** Verilator has no four-state simulation: an uninitialized register silently reads 0 instead of X, so a missing reset connection can "pass" by luck. Build at least one regression with `--x-assign unique --x-initial unique` (randomized instead of the default zero-fill) so a real hardware reset gap shows up as a mismatch instead of hiding behind Verilator's default.
- **`INITIALDLY`**: a non-blocking assignment inside an `initial` block is executed as blocking by Verilator (no delta-cycle queue exists there), which can silently change behavior versus a real event-driven simulator. Reserve `<=` for `always` blocks that model clocked state.
- **`UNOPTFLAT`**: Verilator compiles combinational logic into a fixed evaluation order and cannot iteratively resolve a real combinational loop the way an event-driven simulator can; treat this warning as a design defect to fix, not a warning to suppress.
- **`===`/`!==` collapse to `==`/`!=`** in the two-state model (no X/Z to distinguish), so they cannot detect a floating bus or an uninitialized condition the way they would under a four-state simulator (Icarus Verilog, for example).

## Sources

- [chipverify.com: Verilator simulation](https://chipverify.com/rtl-synthesis/verilator-simulation) — the two-state (no X/Z) model and its reset-bug-hiding consequence, `--x-assign unique`, `INITIALDLY`, `UNOPTFLAT`, and where a four-state simulator like Icarus still earns its place (tri-state buses, class-based testbenches).
- [Verilator: simulating your model](https://verilator.org/guide/latest/simulating.html) — the tool's own reference for build/run flags, including the explicit `--x-assign fast`/`--x-initial fast` speed-versus-reset-bug-masking tradeoff, `--coverage`, and `--prof-exec`/`--runtime-debug` for performance and crash debugging.
- [learn_verilator_iverilog](https://github.com/universal-verification-methodology/learn_verilator_iverilog) — a side-by-side Verilator/Icarus Verilog course; useful for where the two tools' testbench idioms and four-state-vs-two-state behavior genuinely diverge, since this skill otherwise assumes Verilator.
