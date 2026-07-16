# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Changed

- update README links and status after the 0.1.0 publication;
- consolidate future GitHub and Galaxy publication into one guarded release workflow;
- verify role and filter documentation in CI and release builds;
- document Galaxy account-token scope and rotation across repositories.

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
