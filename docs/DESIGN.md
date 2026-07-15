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

1. determine whether a start transition is needed;
2. capture readiness boundaries required before the transition;
3. run `before_start` hooks when a transition will occur;
4. start the systemd unit;
5. verify readiness;
6. run `after_ready` hooks.

### Stop

For every managed service in reverse order and for every resolved host:

1. determine whether a stop transition is needed;
2. run `before_stop` hooks when a transition will occur;
3. stop the systemd unit;
4. run `after_stop` hooks.

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

Supported MVP phases are:

- `before_start`
- `before_stop`
- `after_ready`
- `after_stop`

Task files retain native Ansible behavior such as loops, registers, assertions and delegation. ServiceFlow does not parse task dictionaries embedded in variables.

The hook context will expose the current service, target inventory host, action and phase. Consumer hooks therefore do not need repeated group-membership conditions.

## Readiness

The MVP supports:

- `systemd`: required `ActiveState` and optional `SubState`;
- `log`: a regular expression must occur in data written after the current start boundary.

Log readiness records the file identity and byte offset before starting the service. Existing matching lines cannot satisfy the check. Rotation and truncation behavior must be covered by tests before the feature is accepted.

Port and HTTP checks are useful follow-up features, but standard Ansible modules already cover them and they are not required to prove the orchestration model.

## Validation and check mode

The complete configuration and execution plan must be validated before the first service transition. Validation includes actions, unique service names, unit names, group existence, non-empty resolved hosts, supported hooks and readiness definitions.

Check mode reports the ordered plan. It must not change a service, run mutation hooks or wait for readiness events that depend on a future start.

## Failure behavior

The first implementation stops at the first service, hook or readiness failure and returns structured context. Automatic rollback is deferred until the project can reliably distinguish services changed by the current run from services that were already active.

Unconditional error suppression is not part of the public interface.

## Non-goals

The MVP does not provide:

- arbitrary dependency graphs;
- parallel, rolling or batched execution;
- automatic dependency discovery;
- application-specific integrations;
- container, Kubernetes or Windows service management;
- external Python dependencies.
