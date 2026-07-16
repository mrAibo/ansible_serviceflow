# ServiceFlow lifecycle role

Ordered, cross-host systemd lifecycle orchestration for Ansible.

This role validates the declared service list, resolves target hosts from
inventory groups, and performs an ordered start, reverse-order stop, or full
restart of the configured systemd units. It relies on
`ansible.builtin.systemd_service` for unit transitions and does not reimplement
systemd operations.

## Variables

| Variable | Type | Required | Description |
| --- | --- | --- | --- |
| `serviceflow_action` | string | no, default `start` | `start`, `stop`, or `restart`. |
| `serviceflow_services` | list of dictionaries | yes | Ordered service definitions. |
| `serviceflow_become` | boolean | no, default `true` | Use privilege escalation for service, hook, and readiness operations. |

## Service definitions

Each entry supports:

- `name`: unique logical service name;
- `unit`: systemd unit name;
- `groups`: inventory groups whose hosts run the unit;
- `exclude_groups`: inventory groups whose hosts are excluded;
- `manage`: evaluated boolean that may skip the complete entry;
- `hooks`: task-file hooks keyed by lifecycle phase;
- `ready`: optional systemd or new-log-entry readiness definition.

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
  roles:
    - role: mraibo.serviceflow.lifecycle
```

See the collection [README](../../README.md),
[quick start](../../docs/QUICKSTART.md), and
[configuration reference](../../docs/REFERENCE.md) for full examples.
