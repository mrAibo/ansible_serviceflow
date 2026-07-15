# Ansible ServiceFlow

Dependency-aware systemd service lifecycle orchestration for Ansible.

> **Status:** MVP development. The planner and lifecycle role validate service definitions, resolve inventory-group hosts, execute deterministic start, stop and restart phases, run transition-aware task-file hooks, and verify systemd readiness. New-log-entry readiness is not implemented yet.

ServiceFlow is intended for applications whose services run on different inventory hosts and must be started or stopped in a strict order. It complements `ansible.builtin.systemd_service`; it does not replace it.

## Problem

A conventional playbook often grows into repeated `shell: systemctl ...`, group-based `when` expressions, manual reverse ordering, log manipulation and application-specific tasks mixed into one long file.

ServiceFlow keeps the application definition declarative:

```yaml
serviceflow_action: restart

serviceflow_services:
  - name: backend
    groups: [backend]
    unit: example-backend.service
    ready:
      type: systemd
      active_state: active
      sub_state: running
      timeout: 60
      interval: 2
    hooks:
      after_ready:
        - name: Verify dependent state
          tasks: hooks/verify_state.yml

  - name: worker
    groups: [worker]
    unit: example-worker.service

  - name: api
    groups: [api]
    unit: example-api.service
    hooks:
      before_stop:
        - name: Prepare application shutdown
          tasks: hooks/prepare_shutdown.yml
          vars:
            timeout: 60

  - name: frontend
    groups: [frontend, edge]
    unit: example-frontend.service
```

The declared order is the start order. Stop uses the exact reverse order. Restart performs a complete stop followed by a complete start.

## Hooks

The implemented hook phases are:

- `before_start`
- `before_stop`
- `after_ready`
- `after_stop`

Relative task paths are resolved from the consuming playbook directory. Hook tasks execute on the current service target host by default and retain normal Ansible behavior.

Hook variables are available through `serviceflow_hook_vars`. Lifecycle details are available through `serviceflow_hook_context`:

```yaml
---
- name: Show shutdown context
  ansible.builtin.debug:
    msg: >-
      Preparing {{ serviceflow_hook_context.service }} on
      {{ serviceflow_hook_context.target_host }} with timeout
      {{ serviceflow_hook_vars.timeout }} seconds
```

Hooks run only when the requested systemd state requires a real transition. They do not run in check mode or for an already satisfied state. `after_ready` runs only after a successful readiness check following a real start transition. A hook failure aborts the lifecycle before the following service operation; errors are never suppressed implicitly.

## Systemd readiness

A service can require a systemd state before ServiceFlow advances to the next service:

```yaml
ready:
  type: systemd
  active_state: active
  sub_state: running
  timeout: 60
  interval: 2
```

`active_state` defaults to `active`. `sub_state` is optional. `timeout` and `interval` are positive integers in seconds and default to `60` and `2`.

Readiness is verified after every normal start action, including an idempotent start of an already-active service. This detects a service whose systemd state does not match the declared boundary. Check mode reports the plan but neither waits for readiness nor runs `after_ready` hooks.

A readiness failure stops the lifecycle before the next service is processed and reports the expected and last observed systemd states. Successful checks are returned in `serviceflow_result.readiness`.

New-log-entry readiness remains deferred until file identity, byte-offset, truncation and rotation behavior are implemented and tested.

## MVP

The first release is limited to:

- ordered start and reverse-order stop;
- restart as full stop plus full start;
- target resolution from inventory groups;
- `manage` and `exclude_groups` selection;
- native task-file hooks around service transitions;
- readiness through systemd state or a new log entry;
- check-mode planning;
- structured results and clear validation errors.

Arbitrary dependency graphs, parallel execution, rolling restarts, containers and platform-specific application integrations are intentionally deferred.

See [the MVP design](docs/DESIGN.md) and [issue #1](https://github.com/mrAibo/ansible_serviceflow/issues/1).

## License

GPL-3.0-or-later.
