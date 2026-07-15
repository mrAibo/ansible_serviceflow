# ServiceFlow MVP design

## Decision

The first ServiceFlow release uses one ordered list of services. The list order is the start order. Stop reverses the list. Restart performs the complete stop sequence and then the complete start sequence.

A general dependency graph is deliberately deferred. The ordered model covers the first real multi-host workflow with less code, fewer validation rules and predictable operator output.

## Execution model

The lifecycle role runs from an orchestration play and resolves target hosts through Ansible inventory groups. Service and readiness operations are delegated to the resolved managed hosts.

A service may name multiple groups. Their hosts are merged in inventory order and deduplicated. `exclude_groups` removes matching hosts. `manage` is an already evaluated boolean that can skip the complete service entry.

Service operations use `ansible.builtin.systemd_service`. ServiceFlow adds only ordering, host selection, lifecycle hooks, readiness boundaries and result aggregation.

## Actions

### Start

For every managed service in declared order and for every resolved host:

1. read the current systemd active state without modifying the unit;
2. run `before_start` hooks only when a start transition is required;
3. capture a log boundary when log readiness and a real start transition are configured;
4. request `state: started` through `ansible.builtin.systemd_service`;
5. verify configured readiness;
6. run `after_ready` hooks only after readiness succeeds for a real start transition;
7. record the operation and readiness result.

Systemd readiness is verified for every normal start action, including an already-active service. Log readiness requires a new start boundary and is recorded as skipped when no start transition occurs. Mutation hooks remain transition-aware.

### Stop

For every managed service in reverse order and for every resolved host:

1. read the current systemd active state without modifying the unit;
2. run `before_stop` hooks only when a stop transition is required;
3. request `state: stopped` through `ansible.builtin.systemd_service`;
4. run `after_stop` hooks only after a successful real stop transition;
5. record the operation result.

### Restart

Restart is not a per-service `systemctl restart` loop. It is the full stop action followed by the full start action so that downstream services do not remain active while their dependencies restart.

## Hooks

Implemented phases are `before_start`, `before_stop`, `after_ready` and `after_stop`. Hook task files are supplied by the consuming project and retain native Ansible behavior. Relative paths are resolved from the consuming playbook directory.

Hook values are namespaced under `serviceflow_hook_vars`. Lifecycle context is available under `serviceflow_hook_context` with `action`, `phase`, `service`, `unit` and `target_host`.

Hooks run only for a required transition and never in check mode. `after_ready` requires a readiness definition and runs only after successful readiness following a real start transition.

## Systemd readiness

```yaml
ready:
  type: systemd
  active_state: active
  sub_state: running
  timeout: 60
  interval: 2
```

`active_state` defaults to `active`; `sub_state` is optional. The role performs one immediate `systemctl show` read plus bounded retries. Successful results include observed states and attempt count.

## Log readiness

```yaml
ready:
  type: log
  path: /var/log/example/application.log
  regex: '^Application ready$'
  timeout: 60
  interval: 1
```

The boundary is captured after `before_start` hooks and immediately before systemd starts the unit. It contains whether the path exists, its device, inode and current byte offset. The wait phase examines only bytes written after that boundary.

The implementation handles:

- a file created after capture;
- normal append;
- same-inode truncation by resetting the tracked offset;
- rename-based rotation by locating the previous inode in the same directory and then following the new path identity.

Existing matching content cannot satisfy readiness. Log contents are never modified and are not returned in results. Only counters and file identity metadata are reported.

When no start transition occurs, log readiness is recorded as skipped with reason `no_start_transition`. Waiting for a new startup message from an already-running service would otherwise be unbounded and misleading.

## Validation and check mode

The complete configuration is validated before the first transition. Readiness fields are type-specific. Log paths must be absolute, regular expressions must compile, and timeout and interval values must be positive integers.

Check mode reports the plan and uses native systemd change prediction. It captures no log boundary, waits for no readiness event and runs no mutation hook.

## Failure behavior

The implementation stops at the first service, hook or readiness failure. A readiness failure prevents later services and `after_ready` hooks. A service already started before a timeout remains started; rollback is outside the current scope.

## Non-goals

The MVP does not provide arbitrary dependency graphs, parallel or rolling execution, automatic dependency discovery, application-specific integrations, container or Windows service management, external Python dependencies, or implicit error suppression.
