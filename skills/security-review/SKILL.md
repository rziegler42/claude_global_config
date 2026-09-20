---
name: security-review
description: Review concrete security boundaries involving authentication, authorization, secrets, untrusted input, parsing, filesystems, subprocesses, networks, dependencies, CI, permissions, or deployment.
---

# Focused security review

Review only the security-sensitive scope of the requested change.

1. Identify protected assets, trust boundaries, entry points, and attacker-controlled inputs supported by the actual design.
2. Inspect the smallest relevant implementation, configuration, tests, manifests, and deployment assumptions.
3. Trace authorization, validation, escaping, secret handling, paths, subprocess arguments, network exposure, and failure behavior where applicable.
4. Report reachable, evidence-supported misuse cases rather than a generic checklist.
5. Confirm permissions are no broader than the runtime behavior needs.

Run focused tests at each identified boundary, including a negative or adversarial case when practical. Never request real secrets, attack external systems, install scanners, or perform destructive tests.

Report findings by severity with file/location, reachable impact, smallest correction, verification performed or required, residual risk, and explicit assumptions. If there are no material findings, say so and state the evidence limitations.
