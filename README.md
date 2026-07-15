# Ansible ServiceFlow

Dependency-aware systemd service lifecycle orchestration for Ansible.

> **Status:** Version 0.1.0 is released after successful external acceptance testing.

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
      type: log
      path: /var/log/example/application.log
      regex: '^Application ready$'
      timeout: 120
      interval: 1
    hooks:
      after_ready:
        - name: Verify dependent state
          tasks: hooks/verify_state.yml

  - name: worker
    groups: [worker]
    unit: example-worker.service
    ready:
      type: systemd
      active_state: active
      sub_state: running

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

Use the collection role from an orchestration play:

```yaml
---
- name: Manage the application lifecycle
  hosts: localhost
  gather_facts: false
  roles:
    - role: mraibo.serviceflow.lifecycle
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

```yaml
ready:
  type: systemd
  active_state: active
  sub_state: running
  timeout: 60
  interval: 2
```

`active_state` defaults to `active`. `sub_state` is optional. `timeout` and `interval` are positive integers in seconds and default to `60` and `2`.

Systemd readiness is verified after every normal start action, including an idempotent start of an already-active service. This detects a service whose systemd state does not match the declared boundary.

## New-log-entry readiness

```yaml
ready:
  type: log
  path: /var/log/example/application.log
  regex: '^Application ready$'
  timeout: 60
  interval: 1
```

Before a real start transition, ServiceFlow captures the log file device, inode, byte offset and a small content anchor. After systemd starts the unit, only bytes written after that boundary can satisfy the regular expression. Existing matching lines are ignored.

The log file may be absent when the boundary is captured. Copy-truncate, same-inode rewrites and rename-based rotation are handled. ServiceFlow never removes or rewrites log content.

New bytes are decoded as UTF-8 with replacement for invalid sequences. Regex matching uses a bounded rolling 64-KiB text window, which prevents unbounded memory growth and is intended for readiness messages rather than very large multi-line records.

Log readiness needs an actual start transition. When the service is already active, the check is recorded as skipped with reason `no_start_transition`; ServiceFlow does not wait indefinitely for a new startup message. Check mode captures no boundary, waits for no readiness event and runs no mutation hook.

## Failure behavior and results

A readiness failure stops the lifecycle before the next service is processed. A service that was successfully started before its readiness timeout remains started; automatic rollback is outside the current scope.

Successful and skipped checks are returned in `serviceflow_result.readiness`. Log results include bytes examined, elapsed time, rotation and truncation counts, without returning log contents.

## Version 0.1.0 scope

Version 0.1.0 includes:

- ordered start and reverse-order stop;
- restart as full stop plus full start;
- target resolution from inventory groups;
- `manage` and `exclude_groups` selection;
- native task-file hooks around service transitions;
- readiness through systemd state or a new log entry;
- check-mode planning;
- structured results and clear validation errors.

Arbitrary dependency graphs, parallel execution, rolling restarts, containers and platform-specific application integrations are intentionally deferred.

## Documentation

- [MVP design](docs/DESIGN.md)
- [Acceptance guide](docs/ACCEPTANCE.md)
- [Changelog](CHANGELOG.md)
- [MVP tracker](https://github.com/mrAibo/ansible_serviceflow/issues/1)

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
