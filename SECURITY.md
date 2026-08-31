# Security Policy

## Supported Versions

Engineering Scope Guard is pre-release software. Until the first release, security fixes are made only on the current default branch.

| Version | Supported |
| --- | --- |
| Current default branch | Yes |
| Tagged releases | No tagged release is currently supported |

This table must be updated when the first release is published.

## Reporting a Vulnerability

Use GitHub's private vulnerability reporting for this repository: open the **Security** tab and select **Report a vulnerability**. Please include the affected revision, the realistic impact, reproduction steps, and any relevant local configuration. Do not include secrets or unrelated repository contents.

Do not disclose vulnerability details in a public issue. If private reporting is unavailable, open a public issue stating only that the private reporting channel is unavailable; do not include technical vulnerability details.

We will acknowledge reports when maintainers are available, validate them against the current supported version, and coordinate disclosure after a fix or documented resolution. This pre-release project does not promise a fixed response or release schedule.

## System and Trust Boundaries

V0 is a local Shadow Scope Analyzer. It reads an explicitly selected target repository and representative Codex event data, then writes local machine-readable events and a human-readable report. It is not a network service, security sandbox, policy enforcement layer, or semantic security scanner.

Treat target-repository files, manifests, symbolic links, configuration paths, and Codex JSONL or hook payloads as untrusted input. The analyzer runs with the invoking user's local permissions. Its configured state and output directory is the only intended write boundary and must be outside the target repository.

## Security Invariants

V0 must:

- make no network or telemetry calls;
- never modify the target repository and reject state or output paths that overlap it;
- avoid executing or importing target source, manifests, configuration, or event payloads;
- parse malformed, missing, and oversized inputs with bounded resource use and explicit failure or degraded-health output;
- write only the minimum local structural data required for analysis, and never persist source contents, prompts, reasoning, raw command output, credentials, tokens, or other detected secrets;
- surface missing or unsupported event coverage instead of reporting complete or healthy coverage; and
- prevent path traversal or symbolic-link handling from causing reads or writes outside the configured boundaries.

Local outputs may contain relative file paths, hashes, counts, command classifications, and other structural metadata. Users should treat those outputs as potentially sensitive and keep them local unless they have reviewed them.

## Reportable Findings

Please report a finding when an attacker-controlled repository, configuration, or Codex event payload can realistically cause:

- outbound network communication or data exfiltration;
- modification of the target repository or writes outside the configured state/output directory;
- unintended reads outside the configured target;
- execution of target-controlled code or command injection;
- persistence of source content, prompts, reasoning, raw command output, credentials, tokens, or secrets;
- material denial of service through unbounded parsing or resource consumption; or
- a false healthy/complete coverage result that conceals missing or malformed observation data.

Include a realistic attack path and impact. A tool crash or incorrect scope-budget signal without a security consequence is ordinarily a bug, not a vulnerability.

## Out of Scope and Known Limitations

The following are not security guarantees of V0:

- protection from a malicious local user, administrator, compromised operating system, or compromised Codex installation with equivalent or greater permissions;
- containment of arbitrary code executed separately by Codex or the user;
- semantic correctness of scope-budget signals or a determination that code is "overengineered";
- complete observation of Codex activity where supported event interfaces omit or change events; or
- security of future non-goals such as cloud services, telemetry, dashboards, policy injection, supervising LLMs, automatic cleanup, or multi-agent support.

Upstream Codex defects and generic dependency advisories are reportable here only when they create a reachable violation of this repository's security invariants. The analyzer's health reporting is a compensating control for evolving Codex interfaces; it does not make incomplete observation complete.
