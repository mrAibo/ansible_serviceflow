# Changelog

All notable changes to this project are documented in this file.

## Unreleased

## 0.2.0 - 2026-07-20

### Added

- allow `name` to be omitted and derive it by removing only a final `.service` suffix from `unit`;
- allow `groups` and `exclude_groups` to use either one string or a list of strings.

### Changed

- keep readiness definitions as dictionaries and retain the existing lifecycle and result schema;
- document the concise service input form without adding automatic service or inventory discovery.

## 0.1.1 - 2026-07-20

### Security

- redact hook variable values and names from public lifecycle plans and check-mode output;
- keep the full execution plan private and clear it after lifecycle completion or failure;
- hide plan output unless `serviceflow_show_plan` is explicitly enabled.

### Fixed

- require exactly one orchestration host to prevent duplicate concurrent lifecycle execution;
- use `systemd_service` check-mode preview as the single transition decision source;
- report initial, desired and final systemd states separately;
- correct systemd readiness retry calculation and reject intervals greater than timeouts;
- add the documented result schema version, redacted plan and compatibility phases;
- include requested and phase actions in hook results and `matched` in systemd readiness results;
- validate hook task files on the controller before changing services;
- reject duplicate host and unit targets across logical service entries.

### Changed

- prepare collection metadata for version 0.1.1;
- retain `phases` as a redacted compatibility alias while `plan` is the canonical public plan.

## 0.1.0 - 2026-07-15

### Added

- deterministic ordered start and reverse-order stop;
- full restart as complete stop followed by complete start;
- inventory-group target resolution, deduplication and exclusions;
- evaluated `manage` selection;
- transition-aware native task-file hooks;
- systemd readiness through expected active and optional sub states;
- new-log-entry readiness with pre-start boundaries;
- support for absent log files, append, same-inode rewrites and rename rotation;
- check-mode planning without service, hook or readiness side effects;
- structured operation, hook and readiness results;
- fail-fast configuration validation and lifecycle failure handling;
- collection build, installed-artifact and real systemd integration tests.

### Deferred

- automatic rollback;
- arbitrary dependency graphs;
- parallel or rolling execution;
- port and HTTP readiness;
- non-systemd service managers.
