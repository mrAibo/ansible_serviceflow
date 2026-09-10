# Configuration reference

## Role variables

### `serviceflow_action`

Type: string. Default: `start`.

Allowed values:

- `start`: process services in declared order;
- `stop`: process services in reverse order;
- `restart`: run the complete stop phase, then the complete start phase.

Any other value fails before the first service change.

### `serviceflow_become`

Type: boolean. Default: `true`.

Controls privilege escalation for service transitions, readiness operations and hook task files.

### `serviceflow_parallel_hosts`

Type: boolean. Default: `false`.

When enabled, hosts resolved for the current logical service launch their systemd transition concurrently. Service entries themselves always remain strictly ordered. Start therefore preserves declared dependency order and stop preserves exact reverse dependency order.

Pre-transition hooks and log-readiness boundaries are prepared before the parallel transition jobs begin. ServiceFlow waits for all jobs of the current service before running readiness/post-transition handling and before advancing to the next service.

### `serviceflow_parallel_timeout`

Type: integer seconds. Default: `300`.

Maximum runtime for one asynchronous systemd transition when `serviceflow_parallel_hosts` is enabled. This timeout applies only to the service transition job. Readiness uses the timeout declared in each service's `ready` definition.

### `serviceflow_services`

Type: list of dictionaries. Required and non-empty.

The list order is significant. Every logical service name must be unique.

## Service fields

### `name`

Required non-empty string. A logical identifier used in plans, errors, hook context and structured results. It does not need to equal the systemd unit name.

### `unit`

Required non-empty string containing the systemd unit name. Whitespace is rejected.

```yaml
unit: example-worker.service
```

ServiceFlow does not enable, disable, mask, unmask or edit the unit.

### `groups`

Required non-empty list of inventory group names.

Hosts from all listed groups are combined using OR semantics and deduplicated while preserving stable inventory order.

```yaml
groups:
  - frontend
  - edge
```

A missing group is a configuration error before changes.

### `exclude_groups`

Optional list of inventory group names. Default: empty.

Excluded hosts are removed after the positive groups are merged. If no hosts remain, validation fails before service changes.

```yaml
groups: [frontend, edge]
exclude_groups: [maintenance]
```

### `manage`

Optional boolean. Default: `true`.

```yaml
manage: "{{ environment_name != 'development' }}"
```

The value must already evaluate to a real boolean. Strings such as `"false"` are rejected. When false, the complete entry is skipped and reported with reason `manage=false`.

## Hooks

Optional dictionary keyed by lifecycle phase:

```yaml
hooks:
  before_start: []
  before_stop: []
  after_ready: []
  after_stop: []
```

Every hook entry accepts:

### `name`

Optional descriptive string used in output and results.

### `tasks`

Required path to a native Ansible task file. Relative paths are resolved from `playbook_dir`.

### `vars`

Optional dictionary exposed to the task file as `serviceflow_hook_vars`.

Example:

```yaml
hooks:
  before_stop:
    - name: Drain work
      tasks: hooks/drain.yml
      vars:
        timeout: 30
```

Hook task files also receive:

```yaml
serviceflow_hook_context:
  action: restart
  phase: before_stop
  service: application
  unit: example-application.service
  target_host: app-a.example.invalid
```

Hooks run only when the corresponding state transition is needed. They do not run in check mode. Hook errors abort the lifecycle and are not implicitly ignored.

`after_ready` requires a readiness definition and runs only after a successful readiness check following a real start transition.

## Readiness

Readiness is optional. Without it, ServiceFlow considers a successful `ansible.builtin.systemd_service` call to be the boundary.

Supported types:

- `systemd`;
- `log`.

### Systemd readiness

```yaml
ready:
  type: systemd
  active_state: active
  sub_state: running
  timeout: 60
  interval: 2
```

Fields:

- `type`: required, `systemd`;
- `active_state`: optional expected `ActiveState`, default `active`;
- `sub_state`: optional expected `SubState`;
- `timeout`: positive integer seconds, default `60`;
- `interval`: positive integer seconds, default `2`.

The first state read is immediate. ServiceFlow then retries until the expected state is observed or the timeout is exhausted. Systemd readiness is checked even when the unit was already active.

### New-log-entry readiness

```yaml
ready:
  type: log
  path: /var/log/example/application.log
  regex: '^Application ready$'
  timeout: 120
  interval: 1
```

Fields:

- `type`: required, `log`;
- `path`: required absolute path;
- `regex`: required valid Python regular expression;
- `timeout`: positive integer seconds, default `60`;
- `interval`: positive integer seconds, default `1`.

Immediately before a real start transition, ServiceFlow captures a file boundary. Only bytes written after that boundary can satisfy the regex. Existing matching content is ignored.

Supported file changes:

- file absent at capture and created later;
- normal append;
- same-inode truncation or rewrite;
- rename-based rotation followed by a new file at the configured path.

The matcher incrementally decodes new bytes as UTF-8 with replacement across read-chunk boundaries and retains a bounded 64-KiB rolling text window. Decoder state is reset after rotation or truncation. It is intended for short readiness records, not unbounded multi-megabyte multiline events.

When the service is already active, no new startup boundary exists. The log check is reported as skipped with reason `no_start_transition`.

## Execution order

Services are always sequential. By default, hosts resolved for one service are sequential as well. Set `serviceflow_parallel_hosts: true` to transition hosts of the current service concurrently while preserving the service barrier.

For:

```yaml
serviceflow_services:
  - name: first
  - name: second
```

`start`:

```text
all first hosts → all second hosts
```

`stop`:

```text
all second hosts → all first hosts
```

With parallel host execution, the hosts represented by each `all ... hosts` stage launch concurrently; the arrow remains a strict barrier.

`restart` always completes the whole reverse stop phase before the ordered start phase.

## Failure semantics

The lifecycle stops at the first validation, hook, systemd or readiness error. Later services are not processed.

In parallel mode, service transition jobs for the current service may already be in flight when one host reports an error. ServiceFlow waits through the task's normal async handling but does not provide automatic rollback. A unit that started successfully but failed readiness remains started.

## Check mode

Check mode:

- validates the complete definition;
- returns the planned phases;
- uses native systemd check-mode prediction;
- does not execute hooks;
- does not launch asynchronous service jobs;
- does not capture log boundaries;
- does not wait for future readiness events.

## Fields deliberately not supported

Unknown service fields are rejected. This prevents misspellings or future-looking options from being silently ignored while services are changed.
