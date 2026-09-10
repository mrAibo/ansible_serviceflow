# ServiceFlow lifecycle role

Ordered, cross-host systemd lifecycle orchestration for Ansible.

This role validates the declared service list, resolves target hosts from
inventory groups, and performs an ordered start, reverse-order stop, or full
restart of the configured systemd units. It relies on
`ansible.builtin.systemd_service` for unit transitions and does not reimplement
systemd operations.

Service entries are always processed in strict order. Hosts belonging to one
service entry are sequential by default and can optionally transition in
parallel with `serviceflow_parallel_hosts: true`.

## Variables

| Variable | Type | Required | Description |
| --- | --- | --- | --- |
| `serviceflow_action` | string | no, default `start` | `start`, `stop`, or `restart`. |
| `serviceflow_services` | list of dictionaries | yes | Ordered service definitions. |
| `serviceflow_become` | boolean | no, default `true` | Use privilege escalation for service, hook, and readiness operations. |
| `serviceflow_show_plan` | boolean | no, default `false` | Display the redacted lifecycle plan. |
| `serviceflow_parallel_hosts` | boolean | no, default `false` | Run systemd transitions concurrently for hosts of the same logical service. |
| `serviceflow_parallel_timeout` | integer | no, default `300` | Maximum runtime in seconds for an individual asynchronous systemd transition. |

## Service definitions

Each entry supports:

- `name`: unique logical service name;
- `unit`: systemd unit name;
- `groups`: inventory groups whose hosts run the unit;
- `exclude_groups`: inventory groups whose hosts are excluded;
- `manage`: evaluated boolean that may skip the complete entry;
- `hooks`: task-file hooks keyed by lifecycle phase;
- `ready`: optional systemd or new-log-entry readiness definition.

## Execution model

The declared service list is the start order and its exact reverse is the stop
order. Setting `serviceflow_parallel_hosts: true` changes only execution within
one service entry: all prepared hosts launch their systemd transition
concurrently, then ServiceFlow waits for those jobs and performs readiness and
post-transition handling before moving to the next service entry.

This means a dependency such as database → application → frontend remains
strict even when each tier contains several hosts.

## Hooks

Supported phases are:

- `before_start`;
- `before_stop`;
- `after_ready`;
- `after_stop`.

Hook `tasks` paths are resolved from the consuming playbook directory unless
absolute. Each hook receives `serviceflow_hook_context` and
`serviceflow_hook_vars`.

## Readiness

- `systemd`: wait for expected `ActiveState` and optional `SubState`;
- `log`: wait for a regular expression in bytes written after the current
  start boundary. Historical matching lines are ignored.

## Result

The role sets `serviceflow_result` with `action`, `processed`, `skipped`,
`hooks`, and `readiness`. In check mode no service, hook, or readiness side
effect occurs.

## Example

```yaml
---
- name: Manage an application lifecycle
  hosts: localhost
  gather_facts: false
  vars:
    serviceflow_parallel_hosts: true
  roles:
    - role: mraibo.serviceflow.lifecycle
```

See the collection [README](../../README.md),
[quick start](../../docs/QUICKSTART.md), and
[configuration reference](../../docs/REFERENCE.md) for full examples.
