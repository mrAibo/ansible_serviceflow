# Structured results

After the role completes, `serviceflow_result` contains machine-readable details suitable for debug output, reporting or follow-up assertions.

## Top-level structure

```yaml
serviceflow_result:
  schema_version: 2
  action: restart
  check_mode: false
  plan_only: false
  failure_policy: rollback
  plan: {}
  phases: []
  processed: []
  skipped: []
  hooks: []
  readiness: []
  rollback: []
```

`plan` is the canonical redacted public plan. `phases` remains a redacted compatibility alias. The private execution plan is never stored in the result.

Hook variable names and values are replaced by `has_vars` and `vars_count`. HTTP headers, usernames and passwords are replaced by `has_headers` and `has_auth` markers.

## Processed operations

One entry is recorded per service and host operation:

```yaml
- action: start
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  changed: true
  predicted_change: true
  transition_needed: true
  initial_active_state: inactive
  initial_sub_state: dead
  desired_active_state: active
  final_active_state: active
  final_sub_state: running
  check_mode: false
```

In check mode, final states are `null`; `predicted_change` and `desired_active_state` describe the predicted operation. Plan-only mode produces no processed operations.

## Hook results

Executed hooks identify both the requested lifecycle action and the concrete phase action:

```yaml
- requested_action: restart
  phase_action: start
  phase: after_start
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  name: Warm application cache
```

Hooks that do not run because no transition is required are not reported.

## Readiness results

### Systemd

```yaml
- type: systemd
  service: worker
  unit: example-worker.service
  host: worker-a.example.invalid
  matched: true
  active_state: active
  sub_state: running
  attempts: 1
```

### Log

```yaml
- type: log
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  matched: true
  bytes_read: 128
  elapsed: 2.01
  rotations: 0
  truncations: 0
```

Log content is never returned.

### Port

```yaml
- type: port
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  matched: true
  connect_host: 127.0.0.1
  port: 8080
  elapsed: 1
```

### HTTP

```yaml
- type: http
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  matched: true
  status: 200
  attempts: 2
```

Response bodies, headers and credentials are not returned.

### Journal

```yaml
- type: journal
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  matched: true
  journal_unit: example-application.service
  attempts: 1
```

Only entries after the cursor captured before the current start can satisfy the check.

## Rollback results

With `serviceflow_failure_policy: rollback`, only transitions changed by the current run are restored, in reverse order:

```yaml
- service: application
  unit: example-application.service
  host: app-a.example.invalid
  restored_active_state: inactive
  changed: true
```

Rollback does not execute hooks or readiness checks. The role still fails after rollback so the original lifecycle failure remains visible to automation.

## Skipped definitions

Configuration-level skips currently include `manage=false`:

```yaml
- name: optional-worker
  reason: manage=false
```

## Assertions in consuming playbooks

```yaml
- name: Verify result schema and readiness
  ansible.builtin.assert:
    that:
      - serviceflow_result.schema_version == 2
      - serviceflow_result.skipped | length == 0
      - >-
        serviceflow_result.readiness
        | rejectattr('skipped', 'defined')
        | selectattr('matched', 'equalto', false)
        | list
        | length == 0
```

## Persisting reports

A consuming project may write the redacted result on the controller:

```yaml
- name: Save lifecycle result
  ansible.builtin.copy:
    dest: ./artifacts/serviceflow-result.json
    content: "{{ serviceflow_result | to_nice_json }}\n"
    mode: "0600"
  delegate_to: localhost
```

Hostnames, unit names, task paths, URLs and configured paths may still be operationally sensitive even though hook variables, HTTP secrets and log content are excluded.
