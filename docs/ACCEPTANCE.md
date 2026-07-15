# MVP acceptance guide

This guide verifies the public ServiceFlow contract without using production names, hosts, paths, or application behavior.

## Prerequisites

- Ansible Core 2.15 or newer on the controller;
- Linux target hosts using systemd;
- privilege escalation when the selected units require it;
- at least two harmless test units on separate inventory hosts or inventory aliases.

Do not run a first acceptance test against critical services. Use disposable units or a dedicated test environment.

## 1. Build and install the collection

```bash
rm -rf build collections
mkdir -p build collections

ansible-galaxy collection build --output-path build
archive="$(find build -maxdepth 1 -name 'mraibo-serviceflow-*.tar.gz' -print -quit)"
test -n "$archive"

ansible-galaxy collection install "$archive" -p collections
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \
  ansible-galaxy collection list mraibo.serviceflow
```

Verify the custom module documentation:

```bash
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \
  ansible-doc mraibo.serviceflow.log_readiness
```

## 2. Define a neutral inventory

```ini
[orchestrator]
controller ansible_connection=local

[backend]
backend-test

[frontend]
frontend-test
```

The orchestrator host must be separate from the managed group-selection logic. ServiceFlow resolves targets from the complete inventory, not from the orchestrator's `group_names`.

## 3. Define the lifecycle

```yaml
---
- name: Verify ordered lifecycle
  hosts: orchestrator
  gather_facts: false
  roles:
    - role: mraibo.serviceflow.lifecycle
      vars:
        serviceflow_action: restart
        serviceflow_services:
          - name: backend
            groups: [backend]
            unit: example-backend.service
            ready:
              type: log
              path: /var/log/example/application.log
              regex: '^Application ready$'
              timeout: 60
              interval: 1

          - name: frontend
            groups: [frontend]
            unit: example-frontend.service
            ready:
              type: systemd
              active_state: active
              timeout: 30
```

Adapt only the inventory, unit names, and readiness data in the private acceptance project. Do not copy private values into this collection repository.

## 4. Validate check mode

```bash
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \
  ansible-playbook -i inventory.ini lifecycle.yml --check
```

Confirm that:

- the complete ordered plan is displayed;
- no unit changes state;
- no mutation hook runs;
- no log boundary is captured;
- no readiness wait occurs.

## 5. Validate start order

Run with `serviceflow_action: start` while both units are stopped.

Confirm that:

1. the backend unit starts first;
2. the configured backend readiness boundary succeeds;
3. the frontend unit starts only afterward;
4. `serviceflow_result.processed` preserves that order;
5. `serviceflow_result.readiness` contains the expected checks.

Run the same playbook again. It must be idempotent. Systemd readiness is checked again. Log readiness is recorded as skipped with reason `no_start_transition` because no new start occurred.

## 6. Validate stop and restart order

Run with `serviceflow_action: stop` and confirm the exact reverse order:

```text
frontend -> backend
```

Run with `serviceflow_action: restart` and confirm:

```text
stop frontend -> stop backend -> start backend -> readiness -> start frontend
```

Restart must not be implemented as a per-service restart loop.

## 7. Validate hooks

Attach neutral marker task files to `before_start`, `before_stop`, `after_ready`, and `after_stop`.

Confirm that:

- hooks run on the current target host by default;
- hooks run only for a required transition;
- `after_ready` runs only after successful readiness;
- a failing `before_stop` hook prevents the unit stop;
- hook values are available under `serviceflow_hook_vars`;
- lifecycle context is available under `serviceflow_hook_context`.

## 8. Validate old-log rejection

Before starting the log-ready unit, place an already matching line in its test log. Configure the test unit so that its next start does not write a new matching line.

The lifecycle must time out and stop before the following service. The old line must not satisfy readiness.

Then restore normal test-unit behavior and verify each supported boundary case:

- log absent before start and created afterward;
- normal append;
- copy-truncate or same-inode rewrite;
- rename-based rotation.

ServiceFlow must never delete or rewrite the application log.

## 9. Validate failure behavior

For each failure below, confirm that later services are not processed:

- invalid action or duplicate service name;
- missing or empty target group resolution;
- malformed hook definition;
- malformed readiness definition;
- hook failure;
- systemd readiness mismatch;
- log readiness timeout.

A service that started successfully before a readiness failure remains started. Automatic rollback is deliberately not part of version 0.1.0.

## Acceptance record

Record outside this public repository:

- Ansible Core version;
- target operating system and systemd version;
- inventory topology without credentials;
- actions tested;
- readiness types tested;
- exact pass/fail result;
- any environment-specific limitations.
