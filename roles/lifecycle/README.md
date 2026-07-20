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
| `serviceflow_become` | boolean | no, default `true` | Use privilege escalation for service, hook, readiness, and rollback operations. |
| `serviceflow_show_plan` | boolean | no, default `false` | Display the redacted public plan. |
| `serviceflow_plan_only` | boolean | no, default `false` | Validate configuration and hook files without lifecycle operations. |
| `serviceflow_failure_policy` | string | no, default `fail` | `fail` or transition-scoped `rollback`. |

## Service definitions

Each entry supports:

- `name`: unique logical service name;
- `unit`: systemd unit name;
- `groups`: inventory groups whose hosts run the unit;
- `exclude_groups`: inventory groups whose hosts are excluded;
- `manage`: evaluated boolean that may skip the complete entry;
- `hooks`: task-file hooks keyed by lifecycle phase;
- `ready`: optional readiness definition.

## Hooks

Supported phases are:

- `before_start`;
- `after_start`, immediately after a real start and before readiness;
- `before_stop`;
- `after_ready`;
- `after_stop`.

Hook `tasks` paths are resolved from the consuming playbook directory unless
absolute. Each hook receives `serviceflow_hook_context` and
`serviceflow_hook_vars`. Hook variable names and values are omitted from the
public plan.

## Readiness

- `systemd`: expected `ActiveState` and optional `SubState`;
- `log`: expression in bytes written after the current start boundary;
- `port`: TCP connection using `ansible.builtin.wait_for`;
- `http`: accepted status codes and optional response-content expression;
- `journal`: expression in entries after a pre-start journal cursor.

HTTP credentials and headers are never included in the public plan or result.

## Failure handling

The default `fail` policy stops at the first error. With `rollback`, ServiceFlow
restores only systemd transitions changed by the current run, in reverse order.
It does not run hooks or readiness during rollback.

## Result

The role sets schema-versioned `serviceflow_result` with the redacted plan,
processed operations, hooks, readiness checks, and rollback operations. Check
mode and plan-only mode perform no service, hook, readiness, or rollback side
effects.

## Example

```yaml
---
- name: Manage an application lifecycle
  hosts: localhost
  gather_facts: false
  vars:
    serviceflow_failure_policy: rollback
    serviceflow_services:
      - name: application
        groups: [application]
        unit: example-application.service
        hooks:
          after_start:
            - tasks: hooks/warm_cache.yml
        ready:
          type: http
          url: http://127.0.0.1:8080/health
          status_code: [200, 204]
          timeout: 30
  roles:
    - role: mraibo.serviceflow.lifecycle
```

See the collection [README](../../README.md),
[quick start](../../docs/QUICKSTART.md), and
[configuration reference](../../docs/REFERENCE.md) for full examples.
