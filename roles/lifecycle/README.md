# ServiceFlow lifecycle role

Ordered, cross-host systemd lifecycle orchestration for Ansible.

This role executes the `mraibo.serviceflow.lifecycle` action: it validates the
declared service list, resolves target hosts from inventory groups, then
performs an ordered start, reverse-order stop, or full restart of the
configured systemd units. It relies on `ansible.builtin.systemd_service` for
the actual unit transitions and never reimplements systemd operations.

## Variables

| Variable | Type | Required | Description |
| --- | --- | --- | --- |
| `serviceflow_action` | str | no (default `start`) | `start`, `stop`, or `restart`. |
| `serviceflow_services` | list[dict] | yes | Ordered service definitions. |
| `serviceflow_become` | bool | no (default `true`) | Use privilege escalation for service, hook, and readiness operations. |

### Service definition

| Key | Type | Description |
| --- | --- | --- |
| `name` | str | Unique logical service name. |
| `unit` | str | systemd unit name (no whitespace). |
| `groups` | list[str] | Inventory groups whose hosts run the unit. |
| `exclude_groups` | list[str] | Inventory groups whose hosts are excluded. |
| `manage` | bool | When `false`, the service is skipped. |
| `hooks` | dict | Task-file hooks keyed by phase (`before_start`, `before_stop`, `after_ready`, `after_stop`). |
| `ready` | dict | Optional systemd or new-log-entry readiness definition. |

## Hooks

Hook `tasks` paths are resolved from the consuming playbook directory unless
absolute. Each hook receives `serviceflow_hook_context` (action, phase,
service, unit, target_host) and `serviceflow_hook_vars` (the hook's `vars`).

## Readiness

- `systemd`: wait for expected `ActiveState` (and optional `SubState`).
- `log`: wait for a regular expression in log data written **after** the
  start transition; historical matching lines are ignored.

## Result

The role sets `serviceflow_result` with `action`, `processed`, `skipped`,
`hooks`, and `readiness` entries. In check mode no service, hook, or readiness
side effect occurs.

## Example

```yaml
- hosts: localhost
  gather_facts: false
  roles:
    - role: mraibo.serviceflow.lifecycle
```
