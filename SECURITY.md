# Security Policy

## Supported Versions

Only the latest minor release of Lumo receives security fixes. We don't
backport to older `0.0.x` versions while the project is pre-1.0.

| Version | Supported |
|---------|-----------|
| 0.0.x   | ✅ Latest only |
| < 0.0.1 | ❌ Not supported |

## What counts as a security issue

Lumo is a local-only toolkit — no backend, no telemetry, no network calls
at runtime. The realistic attack surface is small:

- The npm installer (`@onexeor/lumo`) writes files to `~/.lumo/`, the
  chosen AI client's skill directory, and that client's MCP config file.
  Bugs in path handling, JSON merging, or shell-out behaviour count.
- The Python tools (`lumo-mobile`) parse user-supplied JSON. Bugs in
  parsing that would let a malicious layout file cause arbitrary
  filesystem writes or command execution count.
- The MCP server (`lumo-mcp`) exposes those tools over stdio. Bugs that
  let a malicious MCP client trigger writes outside the documented
  paths count.

What **does not** count as a security issue:

- A correctness bug in a WCAG / Fitts / Hick check (file a normal bug
  report — those are not security-sensitive).
- A missing rule, a false positive, a false negative.
- Anything that requires the user to manually install a malicious
  layout / config file from an untrusted source.

## How to report

**Do not file a public GitHub issue for security reports.** Instead:

1. Open a private security advisory:
   <https://github.com/OneXeor-Dev/lumo/security/advisories/new>
2. Or email the repository owner directly (the email on the
   `@OneXeor-Dev` GitHub profile).

Include:

- The Lumo version (npm version of `@onexeor/lumo` and / or PyPI version
  of `lumo-mobile`).
- The minimum reproduction (a command, a JSON, a config).
- What you observed.
- What you expected.

We aim to acknowledge within 48 hours and to ship a fix or workaround in
the next patch release. There is no bug bounty.

## Disclosure

We follow coordinated disclosure: we publish the advisory and the fix
together. Please don't post publicly until we've shipped the fix.
