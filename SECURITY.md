# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities through [GitHub's private vulnerability reporting for this repository](https://github.com/thrilokchaitanya-design/DevGuard/security/advisories/new). Avoid public issues for unpatched security problems. Include reproduction steps and impact, but do not attach real credentials, private CI logs, or customer data.

## Deployment notes

DevGuard is self-hosted software with shared passphrase demo authentication, not individual accounts or tenant isolation. Do not use a shared demo workspace for private logs. Operators are responsible for TLS, secret storage, database access and backups, edge rate limits, retention, and review of AI-provider data handling. The repository has no published support response SLA or certified security status.
