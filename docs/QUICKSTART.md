# Quick start

This example manages three neutral application tiers in a strict lifecycle order.

## Project layout

```text
example-project/
├── inventory.ini
├── requirements.yml
├── lifecycle.yml
├── group_vars/
│   └── all/
│       └── serviceflow.yml
└── hooks/
    ├── prepare_shutdown.yml
    └── verify_ready.yml
```

## 1. Install the collection

`requirements.yml`:

```yaml
---
collections:
  - name: mraibo.serviceflow
    version: "0.1.0"
```

```bash
ansible-galaxy collection install -r requirements.yml
```

## 2. Define the inventory

`inventory.ini`:

```ini
[database]
db-a.example.invalid

[application]
app-a.example.invalid

[frontend]
front-a.example.invalid

[orchestrator]
localhost ansible_connection=local
```

ServiceFlow treats the service list as a global sequence. It does not rely on the task order produced by a normal multi-host play.

## 3. Define the lifecycle

`group_vars/all/serviceflow.yml`:

```yaml
---
serviceflow_action: "{{ requested_action | default('start') }}"
serviceflow_become: true

serviceflow_services:
  - name: database
    unit: example-database.service
    groups:
      - database
    ready:
      type: systemd
      active_state: active
      sub_state: running
      timeout: 60
      interval: 2

  - name: application
    unit: example-application.service
    groups:
      - application
    hooks:
      before_stop:
        - name: Prepare application shutdown
          tasks: hooks/prepare_shutdown.yml
          vars:
            endpoint: http://127.0.0.1:8080/control/drain
      after_ready:
        - name: Verify application state
          tasks: hooks/verify_ready.yml
    ready:
      type: log
      path: /var/log/example/application.log
      regex: '^Application ready$'
      timeout: 120
      interval: 1

  - name: frontend
    unit: example-frontend.service
    groups:
      - frontend
    ready:
      type: systemd
      active_state: active
      timeout: 60
      interval: 2
```

The declared order is the start order:

```text
database → application → frontend
```

Stop automatically reverses it:

```text
frontend → application → database
```

Restart performs the complete stop sequence and then the complete start sequence.

## 4. Add optional hooks

`hooks/prepare_shutdown.yml`:

```yaml
---
- name: Ask the application to drain work
  ansible.builtin.uri:
    url: "{{ serviceflow_hook_vars.endpoint }}"
    method: POST
    status_code:
      - 200
      - 204
  delegate_to: localhost
  changed_when: true
```

`hooks/verify_ready.yml`:

```yaml
---
- name: Display the completed lifecycle boundary
  ansible.builtin.debug:
    msg: >-
      {{ serviceflow_hook_context.service }} is ready on
      {{ serviceflow_hook_context.target_host }}.
```

Relative hook paths are resolved from `playbook_dir`. In this layout, `hooks/prepare_shutdown.yml` is correct. Do not repeat the playbook directory in the path.

## 5. Create the orchestration play

`lifecycle.yml`:

```yaml
---
- name: Manage the application lifecycle
  hosts: orchestrator
  gather_facts: false
  roles:
    - role: mraibo.serviceflow.lifecycle
  post_tasks:
    - name: Show the structured result
      ansible.builtin.debug:
        var: serviceflow_result
```

The orchestration play should target one controller-side inventory host, commonly localhost. ServiceFlow resolves and delegates the individual service operations to the managed hosts.

## 6. Preview with check mode

```bash
ansible-playbook -i inventory.ini lifecycle.yml \
  --check \
  -e requested_action=restart
```

Check mode validates the complete definition and predicts systemd changes. It does not run hooks, capture log boundaries or wait for future readiness messages.

## 7. Run lifecycle actions

```bash
ansible-playbook -i inventory.ini lifecycle.yml -e requested_action=start
ansible-playbook -i inventory.ini lifecycle.yml -e requested_action=stop
ansible-playbook -i inventory.ini lifecycle.yml -e requested_action=restart
```

## 8. Recommended first production use

1. Pin version `0.1.0` in `requirements.yml`.
2. Run `--syntax-check`.
3. Run `--check` against the target inventory.
4. Test with non-production units or a maintenance environment.
5. Add one service at a time.
6. Use explicit readiness for every service whose dependants must not start immediately after `systemctl start` returns.
7. Keep application-specific task files in the consuming project, not in the collection.