# Structured results

After the role completes, `serviceflow_result` contains machine-readable details suitable for debug output, reporting or follow-up assertions.

## Top-level structure

```yaml
serviceflow_result:
  schema_version: 1
  action: restart
  check_mode: false
  plan: {}
  phases: []
  processed: []
  skipped: []
  hooks: []
  readiness: []
```

`plan` is the canonical redacted public plan. `phases` is a redacted compatibility alias retained for the 0.1 release line.

The private execution plan is never stored in `serviceflow_result`. Hook variable names and values are replaced by `has_vars` and `vars_count` metadata.

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

In check mode, `final_active_state` and `final_sub_state` are `null`; `predicted_change` and `desired_active_state` describe the predicted operation.

## Skipped definitions

Configuration-level skips currently include `manage=false`:

```yaml
- name: optional-worker
  reason: manage=false
```

This differs from a log readiness check being skipped because no start transition occurred.

## Hook results

Executed hooks identify both the requested lifecycle action and the concrete phase action:

```yaml
- requested_action: restart
  phase_action: stop
  phase: before_stop
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  name: Drain application work
```

Hooks that do not run because no transition is required are not reported as executed.

## Readiness results

### Systemd readiness

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

### Log readiness

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

### Skipped log readiness

When a service is already active, no new start boundary exists:

```yaml
- type: log
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  skipped: true
  reason: no_start_transition
```

## Assertions in consuming playbooks

```yaml
- name: Verify result schema and readiness
  ansible.builtin.assert:
    that:
      - serviceflow_result.schema_version == 1
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

Hostnames, unit names, task paths and configured log paths may still be operationally sensitive even though hook variables and log contents are excluded.
