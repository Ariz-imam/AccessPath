# Changelog

## 0.2.0 — GitHub-ready reliability pass

- Separated administrator maintenance status from verified-report routing restrictions.
- Added report lifecycle transition validation and conflict responses for invalid transitions.
- Added typed status validation and stricter request-model validation.
- Added consistent routing-state reads, fail-closed handling for missing accessibility/status data, and a database-backed health check.
- Made tests use an isolated temporary SQLite database per test.
- Expanded routing and API regression coverage to 35 tests.
- Added development dependencies, repository contribution/security notes, and GitHub Actions CI.
- Updated Windows setup guidance to avoid PowerShell activation-policy problems.

## 0.1.0 — Initial MVP

- Added a schematic 18-node / 19-edge campus graph.
- Added profile-aware weighted routing with NetworkX / Dijkstra.
- Added simulated facility and path status controls.
- Added barrier reporting and administrator review UI.
