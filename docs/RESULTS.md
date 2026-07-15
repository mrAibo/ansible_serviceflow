# Structured results

After the role completes, `serviceflow_result` contains machine-readable details suitable for debug output, reporting or follow-up assertions.

## Top-level structure

```yaml
serviceflow_result:
  action: restart
  check_mode: false
  plan: {}
  processed: []
  skipped: []
  hooks: []
  readiness: []
```

Exact entries depend on the requested action and configured safeguards.

## `action`

The validated lifecycle action: `start`, `stop` or `restart`.

## `check_mode`

Boolean indicating whether Ansible check mode was active.

## `plan`

The validated global plan, including lifecycle phases and resolved services. It is useful for explaining the sequence before or after execution.

## `processed`

One entry per service host operation. Typical fields:

```yaml
- action: start
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  changed: true
  transition_needed: true
  check_mode: false
  initial_state: inactive
  active_state: active
```

Field meanings:

- `action`: operation performed for this phase;
- `service`: logical service name;
- `unit`: systemd unit;
- `host`: resolved inventory host;
- `changed`: result reported by the systemd operation;
- `transition_needed`: whether the initial state required an actual transition;
- `initial_state`: observed state before mutation;
- `check_mode`: whether this operation was predicted rather than executed;
- `active_state`: state returned after the operation when available.

## `skipped`

Configuration-level skips, currently including `manage=false`:

```yaml
- name: optional-worker
  reason: manage=false
```

This is different from readiness being skipped because no start transition occurred.

## `hooks`

Executed hooks are recorded with lifecycle context. A typical entry identifies:

```yaml
- action: restart
  phase: before_stop
  service: application
  unit: example-application.service
  host: app-a.example.invalid
  name: Drain application work
```

Hooks that do not run because no transition is required are not reported as executed.

## `readiness`

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

Log content is not returned. The configured regular expression may appear in the validated plan, but matching application lines are not copied into results.

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
- name: Verify that no service was skipped by configuration
  ansible.builtin.assert:
    that:
      - serviceflow_result.skipped | length == 0

- name: Verify all performed readiness checks matched
  ansible.builtin.assert:
    that:
      - >-
        serviceflow_result.readiness
        | rejectattr('skipped', 'defined')
        | selectattr('matched', 'equalto', false)
        | list
        | length == 0
```

## Persisting reports

A consuming project may write a redacted JSON report on the controller:

```yaml
- name: Save lifecycle result
  ansible.builtin.copy:
    dest: ./artifacts/serviceflow-result.json
    content: "{{ serviceflow_result | to_nice_json }}\n"
    mode: "0600"
  delegate_to: localhost
```

Review the result before storing it in a shared location. Hostnames, unit names and configured paths may be operationally sensitive even though log contents and secrets are not intentionally returned.