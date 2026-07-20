# Ansible ServiceFlow

[![CI](https://github.com/mrAibo/ansible_serviceflow/actions/workflows/ci.yml/badge.svg)](https://github.com/mrAibo/ansible_serviceflow/actions/workflows/ci.yml)
[![Ansible Galaxy](https://img.shields.io/ansible/collection/v/mraibo/serviceflow)](https://galaxy.ansible.com/ui/repo/published/mraibo/serviceflow/)

Ordered, cross-host systemd lifecycle orchestration for Ansible.

> **Status:** Version 0.1.0 is published. Version 0.1.1 is the current bug-fix candidate for lifecycle safety, result correctness and plan redaction.

ServiceFlow manages application stacks whose services live in different inventory groups and must follow one strict lifecycle order. It complements `ansible.builtin.systemd_service`; it does not replace or reimplement it.

## Why ServiceFlow

A normal Ansible playbook manages individual units well. ServiceFlow adds one application-level lifecycle contract:

```text
ordered service list
+ inventory group resolution
+ transition-aware task-file hooks
+ systemd or current-start log readiness
+ automatic reverse stop
+ redacted structured lifecycle result
```

Start follows the declared order. Stop uses the exact reverse order. Restart performs a complete stop sequence followed by a complete start sequence.

## Installation

Until 0.1.1 is released, install the published version:

```bash
ansible-galaxy collection install mraibo.serviceflow:0.1.0
```

Recommended `requirements.yml`:

```yaml
---
collections:
  - name: mraibo.serviceflow
    version: "0.1.0"
```

Requirements:

- `ansible-core >= 2.15`;
- Linux managed hosts using systemd;
- Python available for Ansible module execution;
- appropriate become permissions;
- exactly one orchestration host in the play.

## Minimal example

```yaml
---
- name: Manage an application lifecycle
  hosts: localhost
  gather_facts: false
  vars:
    serviceflow_action: "{{ requested_action | default('restart') }}"
    serviceflow_services:
      - name: database
        groups: [database]
        unit: example-database.service
        ready:
          type: systemd
          active_state: active
          sub_state: running

      - name: application
        groups: [application]
        unit: example-application.service
        hooks:
          before_stop:
            - name: Prepare graceful shutdown
              tasks: hooks/prepare_shutdown.yml
        ready:
          type: log
          path: /var/log/example/application.log
          regex: '^Application ready$'
          timeout: 120
          interval: 1

      - name: frontend
        groups: [frontend, edge]
        exclude_groups: [maintenance]
        unit: example-frontend.service
  roles:
    - role: mraibo.serviceflow.lifecycle
```

## Key behavior

- Services and resolved hosts are processed sequentially.
- Hosts from multiple groups are merged and deduplicated.
- Duplicate combinations of target host and systemd unit are rejected.
- `exclude_groups` removes maintenance or otherwise excluded hosts.
- `manage` must evaluate to a boolean and can skip a complete service entry.
- Hooks are native task files: `before_start`, `before_stop`, `after_ready`, `after_stop`.
- Hook task files are checked on the controller before the first service change.
- Systemd transition prediction uses `ansible.builtin.systemd_service` in check mode.
- Results distinguish initial, desired and final systemd state.
- Systemd readiness checks expected `ActiveState` and optional `SubState`.
- Log readiness accepts only bytes written after the current start boundary.
- Log boundaries are captured atomically from one open file descriptor.
- UTF-8 decoding is preserved across binary read chunks.
- Check mode predicts changes without running hooks or readiness waits.
- Public plans omit hook variable names and values.
- Plan output is disabled by default and may be enabled with `serviceflow_show_plan: true`.
- The lifecycle stops on the first validation, hook, service or readiness failure.
- Automatic rollback is not provided in the 0.1 release line.

## Result schema

Version 0.1.1 returns:

```yaml
serviceflow_result:
  schema_version: 1
  action: restart
  check_mode: false
  plan: {}
  phases: []
  processed: []
  skipped: []
  hooks: []
  readiness: []
```

`plan` and the compatibility `phases` field are redacted. The private execution plan is not returned.

## Documentation

- [Installation and compatibility](docs/INSTALLATION.md)
- [Quick start](docs/QUICKSTART.md)
- [Complete configuration reference](docs/REFERENCE.md)
- [Lifecycle hooks](docs/HOOKS.md)
- [Structured results](docs/RESULTS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Migration and comparison](docs/MIGRATION_AND_COMPARISON.md)
- [Architecture and execution model](docs/DESIGN.md)
- [External acceptance guide](docs/ACCEPTANCE.md)
- [Release process](docs/RELEASING.md)
- [Changelog](CHANGELOG.md)

Installed documentation is also available through:

```bash
ansible-doc -t role mraibo.serviceflow.lifecycle
ansible-doc -t filter mraibo.serviceflow.serviceflow_plan
ansible-doc mraibo.serviceflow.log_readiness
```

## Deferred functionality

- arbitrary dependency graphs;
- parallel or rolling execution;
- automatic rollback;
- HTTP and port readiness;
- non-systemd service managers;
- container and Kubernetes lifecycle management.

## Security

Application hooks are trusted code owned by the consuming project. Keep secrets in Ansible Vault or an approved secret backend and use `no_log` for sensitive operations. Hook variables are available to the private execution path but are not included in the public plan or result.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
