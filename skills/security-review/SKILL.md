---
name: security-review
description: Use when reviewing a change or component that touches authentication, authorization, secrets, untrusted input, parsing, filesystems, subprocesses, networks, dependencies, CI, permissions, or deployment, or when asked for a security audit, injection check, or hardening pass.
---

# Focused security review

Review only the security-sensitive scope of the requested change or component.

1. Identify protected assets, trust boundaries, entry points, and attacker-controlled inputs supported by the actual design. When the repository or a job may be untrusted, treat repository-controlled files (configs, hooks, manifests, build files), any tool, log, or job output an agent consumes, and any state file an untrusted component can rewrite (job metadata, caches) as attacker-controlled; such state must not drive privileged decisions such as which path to read or delete.
2. Inspect the smallest relevant implementation, configuration, tests, manifests, and deployment assumptions.
3. Trace authorization, validation, escaping, secret handling, paths, subprocess arguments, network exposure, and failure behavior where applicable. Validate values before they reach a shell or remote command, not after. Check path guards on resolved, case-normalized paths (symlinks, case-insensitive filesystems), and test how a guard meant to prevent mistakes can be bypassed, not only its normal path. Test containment guards in both directions: a target inside the protected path, and a target that contains it.
4. Report reachable, evidence-supported misuse cases rather than a generic checklist.
5. Confirm permissions are no broader than the runtime behavior needs.

Run focused tests at each identified boundary, including a negative or adversarial case when practical, using previews, dry runs, fake executables, and scratch copies. Never request real secrets, attack external systems, install scanners, or perform destructive tests.

When fixing findings, add a regression test for each that fails before the fix and passes after, and check every fix against existing configuration and callers for legitimate-use regressions. A fix is new attack surface: have an independent reviewer try to bypass it before calling the work done.

Report findings by severity, rated by reachable impact and the attacker position required (Critical, High, Medium, Low), with file/location, reachable impact, smallest correction, verification performed or required, residual risk, and explicit assumptions. List what was checked and found sound so it is not re-reviewed. If there are no material findings, say so and state the evidence limitations.
