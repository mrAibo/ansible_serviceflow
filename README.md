# Ansible ServiceFlow

[![CI](https://github.com/mrAibo/ansible_serviceflow/actions/workflows/ci.yml/badge.svg)](https://github.com/mrAibo/ansible_serviceflow/actions/workflows/ci.yml)
[![Ansible Galaxy](https://img.shields.io/ansible/collection/v/mraibo/serviceflow)](https://galaxy.ansible.com/ui/repo/published/mraibo/serviceflow/)

Ordered, cross-host systemd lifecycle orchestration for Ansible.

> **Status:** Version 0.1.0 is published on [Ansible Galaxy](https://galaxy.ansible.com/ui/repo/published/mraibo/serviceflow/) and available as a [GitHub Release](https://github.com/mrAibo/ansible_serviceflow/releases/tag/0.1.0).

ServiceFlow manages application stacks whose services live in different inventory groups and must follow one strict lifecycle order. It complements `ansible.builtin.systemd_service`; it does not replace or reimplement it.

## Why ServiceFlow

A normal Ansible playbook can manage individual units very well. It becomes harder to keep correct when an application needs all of the following at once:

- one global start order across multiple inventory groups;
- the exact reverse order for stop;
- a complete stop-then-start restart;
- application tasks immediately before or after a service boundary;
- readiness stronger than `systemctl start` returning successfully;
- a log message produced by the current start, not an old matching line;
- complete configuration validation before the first service changes;
- one structured result for the entire lifecycle.

ServiceFlow provides that orchestration contract while continuing to use Ansible built-ins for resource operations.

## How it differs from standard modules and community collections

`ansible.builtin.systemd_service` remains the correct tool for one unit operation. `ansible.builtin.wait_for`, `uri` and `service_facts` remain the correct general-purpose tools for their individual tasks. Community collections also provide many useful resource modules.

ServiceFlow is different because it coordinates those operations as one application lifecycle:

```text
ordered service list
+ inventory group resolution
+ transition-aware task-file hooks
+ systemd or current-start log readiness
+ automatic reverse stop
+ structured lifecycle result
```

It deliberately does not add another systemd client, dependency framework or application-specific plugin system. See [Migration and comparison](docs/MIGRATION_AND_COMPARISON.md) for detailed examples and guidance on when not to use ServiceFlow.

## Installation

Install the published collection from Ansible Galaxy:

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
- appropriate become permissions.

See [Installation and compatibility](docs/INSTALLATION.md).

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

Start order:

```text
database → application → frontend
```

Stop order:

```text
frontend → application → database
```

Restart performs the complete stop sequence followed by the complete start sequence.

For a copyable project layout, inventory, hooks and commands, see [Quick start](docs/QUICKSTART.md).

## Key behavior

- Services and resolved hosts are processed sequentially.
- Hosts from multiple groups are merged and deduplicated.
- `exclude_groups` removes maintenance or otherwise excluded hosts.
- `manage` must evaluate to a boolean and can skip a complete service entry.
- Hooks are native task files: `before_start`, `before_stop`, `after_ready`, `after_stop`.
- Systemd readiness checks expected `ActiveState` and optional `SubState`.
- Log readiness accepts only bytes written after the current start boundary.
- Existing matching log lines are ignored.
- Log files are never deleted, rewritten or returned in results.
- Check mode validates and predicts without running hooks or waiting for future readiness.
- The lifecycle stops on the first validation, hook, service or readiness failure.
- Version 0.1.0 does not automatically roll back a unit that started but failed readiness.

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

## Version 0.1.0 scope

Included:

- ordered start and reverse-order stop;
- restart as full stop plus full start;
- group resolution, deduplication, exclusions and `manage` selection;
- transition-aware task-file hooks;
- systemd readiness;
- new-log-entry readiness with rotation and truncation handling;
- check-mode planning;
- structured results and fail-fast validation.

Deferred:

- arbitrary dependency graphs;
- parallel or rolling execution;
- automatic rollback;
- HTTP and port readiness;
- non-systemd service managers;
- container and Kubernetes lifecycle management.

## Security

Application hooks are trusted code owned by the consuming project. Keep secrets in Ansible Vault or an approved secret backend, use `no_log` for sensitive operations and never commit product-specific hosts, credentials or proprietary log content to this repository.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
