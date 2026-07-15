# Lifecycle hooks

Hooks let a consuming project place normal Ansible task files around systemd transitions without embedding application-specific behavior into ServiceFlow.

## Supported phases

### `before_start`

Runs before a required start transition.

Typical uses:

- validate configuration files;
- prepare directories or runtime state;
- acquire an application lock;
- enable maintenance mode;
- verify an external prerequisite.

### `before_stop`

Runs before a required stop transition.

Typical uses:

- stop application modules cleanly;
- drain work queues;
- remove a node from a load balancer;
- reject new sessions;
- flush application state.

A failure prevents the systemd stop.

### `after_ready`

Runs only after configured readiness succeeds following a real start transition.

Typical uses:

- verify dependent components;
- add a node back to a load balancer;
- disable maintenance mode;
- register the application in discovery;
- perform a lightweight smoke test.

### `after_stop`

Runs after a successful real stop transition.

Typical uses:

- remove temporary files;
- confirm sessions are gone;
- release maintenance locks;
- record an operational event.

## Hook definition

```yaml
hooks:
  before_stop:
    - name: Drain application work
      tasks: hooks/drain.yml
      vars:
        endpoint: http://127.0.0.1:8080/control/drain
        timeout: 30
```

`tasks` points to a native Ansible task file. ServiceFlow does not parse or reinterpret its tasks.

## Path resolution

Relative task paths are resolved from `playbook_dir`.

For this layout:

```text
project/
├── lifecycle.yml
└── hooks/
    └── drain.yml
```

use:

```yaml
tasks: hooks/drain.yml
```

When the playbook itself is in `playbooks/lifecycle.yml`, a sibling top-level `hooks` directory requires:

```yaml
tasks: ../hooks/drain.yml
```

Do not prefix a path with the playbook directory twice.

## Variables

Hook-specific values are namespaced:

```yaml
serviceflow_hook_vars:
  endpoint: http://127.0.0.1:8080/control/drain
  timeout: 30
```

Lifecycle context is available as:

```yaml
serviceflow_hook_context:
  action: restart
  phase: before_stop
  service: application
  unit: example-application.service
  target_host: app-a.example.invalid
```

This avoids injecting arbitrary hook keys into the general Ansible variable namespace.

## Execution host

A hook normally executes in the context of the current service target host. Standard Ansible directives remain available inside the task file.

To call a control-plane endpoint from the controller:

```yaml
---
- name: Drain the current target
  ansible.builtin.uri:
    url: "{{ serviceflow_hook_vars.endpoint }}"
    method: POST
    body_format: json
    body:
      target: "{{ serviceflow_hook_context.target_host }}"
  delegate_to: localhost
```

To execute a command on the managed host, omit `delegate_to`.

## Error handling

Hook failures are fatal. ServiceFlow intentionally does not provide an `ignore_errors` hook policy in 0.1.0.

Use native Ansible `block`, `rescue` and explicit assertions inside the task file when recovery is genuinely required:

```yaml
---
- name: Prepare shutdown
  block:
    - name: Request graceful shutdown
      ansible.builtin.uri:
        url: "{{ serviceflow_hook_vars.endpoint }}"
        method: POST
        status_code: 204
  rescue:
    - name: Explain why shutdown cannot continue
      ansible.builtin.fail:
        msg: >-
          Graceful shutdown failed for
          {{ serviceflow_hook_context.service }} on
          {{ serviceflow_hook_context.target_host }}.
```

Do not hide a failed safety step with broad `ignore_errors: true`.

## Check mode and idempotence

Hooks do not run in check mode. A hook is also skipped when the requested systemd state is already satisfied.

Consequences:

- repeated `start` does not repeat `before_start`;
- repeated `stop` does not repeat `before_stop` or `after_stop`;
- `after_ready` runs only after readiness for a real start transition.

Hook task files should still be written idempotently because a failed run may be retried after only part of the hook completed.

## Why task files instead of inline tasks

Embedding arbitrary Ansible tasks in variables would require ServiceFlow to reproduce Ansible semantics for `register`, loops, conditions, blocks, delegation, tags, privilege escalation and error handling.

Task files preserve:

- native syntax checking;
- `ansible-lint` support;
- editor tooling;
- normal variable and delegation behavior;
- independent tests;
- a clear separation between generic lifecycle orchestration and application behavior.

## Security guidance

Hooks are trusted code from the consuming project.

- Store secrets in Ansible Vault or an approved secret backend.
- Do not put credentials directly into `serviceflow_services`.
- Use `no_log: true` on tasks handling sensitive values.
- Review any hook that uses `shell`, `command`, remote APIs or destructive file operations.
- Keep product-specific hooks outside the public ServiceFlow repository.