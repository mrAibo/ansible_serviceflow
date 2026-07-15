# ServiceFlow MVP design

## Decision

The first ServiceFlow release uses one ordered list of services. The list order is the start order. Stop reverses the list. Restart performs the complete stop sequence and then the complete start sequence.

A general dependency graph is deliberately deferred. The ordered model covers the first real multi-host workflow with less code, fewer validation rules and predictable operator output.

## Execution model

The lifecycle role runs from an orchestration play and resolves target hosts through Ansible inventory groups. Service operations are delegated to the resolved managed hosts.

A service may name multiple groups. Their hosts are merged in inventory order and deduplicated. `exclude_groups` removes matching hosts. `manage` is an already evaluated boolean that can skip the complete service entry.

Service operations use `ansible.builtin.systemd_service`. ServiceFlow adds only ordering, host selection, lifecycle hooks, readiness boundaries and result aggregation.

## Actions

### Start

For every managed service in declared order and for every resolved host:

1. read the current systemd active state without modifying the unit;
2. run `before_start` hooks only when a start transition is required;
3. request `state: started` through `ansible.builtin.systemd_service`;
4. record the initial state, predicted or actual change and final status.

Readiness and `after_ready` will be inserted after the systemd start when their boundaries are implemented.

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

Hooks reference normal Ansible task files supplied by the consuming project:

```yaml
hooks:
  before_stop:
    - name: Prepare application shutdown
      tasks: hooks/prepare_shutdown.yml
      vars:
        shutdown_timeout: 60
```

The implemented phases are:

- `before_start`
- `before_stop`
- `after_stop`

`after_ready` remains reserved and is rejected until readiness itself is implemented.

Relative task paths are resolved from the consuming playbook directory. Absolute paths are accepted. Included hook tasks execute on the current service target host by default and retain native Ansible behavior such as loops, registers, assertions and explicit task-level delegation.

Hook-supplied values are namespaced under `serviceflow_hook_vars`. ServiceFlow exposes a separate `serviceflow_hook_context` mapping with:

- `action`
- `phase`
- `service`
- `unit`
- `target_host`

ServiceFlow does not parse task dictionaries embedded in variables. Hook task files are normal Ansible files and failures stop the lifecycle naturally.

Hooks run only for a required transition. They do not run for an already satisfied state or in check mode.

## Readiness

The remaining MVP will support:

- `systemd`: required `ActiveState` and optional `SubState`;
- `log`: a regular expression must occur in data written after the current start boundary.

Log readiness records the file identity and byte offset before starting the service. Existing matching lines cannot satisfy the check. Rotation and truncation behavior must be covered by tests before the feature is accepted.

Port and HTTP checks are useful follow-up features, but standard Ansible modules already cover them and they are not required to prove the orchestration model.

## Validation and check mode

The complete configuration and execution plan must be validated before the first service transition. Current validation includes actions, unique service names, unit names, group existence, non-empty resolved hosts, supported hook phases, hook task paths and hook variable mappings.

Unknown service fields and deferred readiness definitions fail before a service is changed.

Check mode reports the ordered plan and uses native `systemd_service` change prediction. It does not change a service, run mutation hooks or wait for readiness events that depend on a future start.

## Failure behavior

The implementation stops at the first service or hook failure. A failing `before_stop` hook prevents the unit stop; errors are not suppressed.

Automatic rollback is deferred until the project can reliably distinguish services changed by the current run from services that were already active.

## Non-goals

The MVP does not provide:

- arbitrary dependency graphs;
- parallel, rolling or batched execution;
- automatic dependency discovery;
- application-specific integrations;
- container, Kubernetes or Windows service management;
- external Python dependencies.
