# Security policy

## Current project status

AccessPath is a local demonstration prototype. Its facilities administration endpoints do not have authentication or authorization, and it is not hardened for untrusted network access.

**Do not expose the development server to the public internet or an untrusted network.** Keep it bound to localhost during demonstrations.

## Reporting a vulnerability

Please do not include passwords, tokens, personal information, or sensitive campus access details in public issue reports. Contact the repository maintainers privately after the project owner has configured a security contact for the GitHub repository.

Before any production deployment, implement authenticated roles, authorization checks on every admin/report-review endpoint, input and rate-limit controls, audit logging, secure transport, backups, and a documented incident-response process.
