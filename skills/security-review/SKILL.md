---
name: security-review
description: Use when reviewing a change or component that touches authentication, authorization, secrets, untrusted input, parsing, filesystems, subprocesses, networks, dependencies, CI, permissions, or deployment, or when asked for a security audit, injection check, or hardening pass.
---

# Focused security review

Review only the security-sensitive scope of the requested change or component.

1. Identify protected assets, trust boundaries, entry points, and attacker-controlled inputs supported by the actual design. When the repository or a job may be untrusted, treat repository-controlled files (configs, hooks, manifests, build files), any tool, log, or job output an agent consumes, any state file an untrusted component can rewrite (job metadata, caches), and any name the untrusted side chooses that becomes a key or path (project IDs, cache keys) as attacker-controlled. Such state and names must not drive privileged decisions, such as which path to read or delete or which shared state to reuse.
2. Inspect the smallest relevant implementation, configuration, tests, manifests, and deployment assumptions.
3. Trace authorization, validation, escaping, secret handling, paths, subprocess arguments, network exposure, and failure behavior where applicable, then try these bypasses at each boundary:
   - Shell or remote command: validate values before they reach the shell, not after, and quote every argument. Trace every argument on the command line back to its origin, including values you assume are encoded or validated, and run hostile values through the real code path with a fake executable that records what it receives.
   - Path guards: check resolved, case-normalized paths (symlinks, case-insensitive filesystems), and test containment in both directions, a target inside the protected path and a target that contains it.
   - Edge values at each input: empty, leading `-`, `..`, non-finite or huge numbers, wrong types, case variants.
   - Validation must fail closed: reject unknown or invalid input instead of ignoring it.
   - Guards meant to prevent mistakes: test how each can be bypassed, not only its normal path.
4. Report reachable, evidence-supported misuse cases rather than a generic checklist.
5. Confirm permissions are no broader than the runtime behavior needs.

Run focused tests at each identified boundary, including a negative or adversarial case when practical, using previews, dry runs, fake executables, and scratch copies. Never request real secrets, attack external systems, or install scanners. Perform destructive operations only on throwaway data you created for the test.

When fixing findings, add a regression test for each that fails before the fix and passes after, and check every fix against existing configuration and callers for legitimate-use regressions. A fix is new attack surface: have an independent reviewer try to bypass it before calling the work done.

Report findings by severity, rated by reachable impact and the attacker position required (Critical, High, Medium, Low), with file/location, reachable impact, smallest correction, verification performed or required, residual risk, and explicit assumptions. List what was checked and found sound so it is not re-reviewed, marking each as verified by test or by reading only. Do not call a boundary sound on reading alone when a test is practical: exercise it, for example with a fake executable that records the arguments it receives. If there are no material findings, say so and state the evidence limitations.
