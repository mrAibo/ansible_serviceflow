# ServiceFlow examples

This guide contains copy-ready examples for the most common ServiceFlow use cases. The examples assume that the collection is installed and that the playbook runs from exactly one orchestration host, normally `localhost`.

## Contents

- [Example inventory](#example-inventory)
- [Minimal start, stop and restart](#minimal-start-stop-and-restart)
- [Use an action passed on the command line](#use-an-action-passed-on-the-command-line)
- [Manage a multi-tier application](#manage-a-multi-tier-application)
- [Target several inventory groups](#target-several-inventory-groups)
- [Exclude maintenance hosts](#exclude-maintenance-hosts)
- [Skip optional services](#skip-optional-services)
- [Wait for systemd readiness](#wait-for-systemd-readiness)
- [Wait for a new log message](#wait-for-a-new-log-message)
- [Run lifecycle hooks](#run-lifecycle-hooks)
- [Use hook variables and context](#use-hook-variables-and-context)
- [Run without privilege escalation](#run-without-privilege-escalation)
- [Preview changes with check mode](#preview-changes-with-check-mode)
- [Display the redacted execution plan](#display-the-redacted-execution-plan)
- [Read the structured result](#read-the-structured-result)
- [Keep service definitions in a separate file](#keep-service-definitions-in-a-separate-file)
- [Complete production-style example](#complete-production-style-example)

## Example inventory

```ini
[database]
db01.example.com

[application]
app01.example.com
app02.example.com

[frontend]
web01.example.com
web02.example.com

[edge]
web02.example.com
proxy01.example.com

[maintenance]
app02.example.com
web02.example.com
```

ServiceFlow resolves managed hosts from the groups declared for every service. Hosts from several positive groups are merged and deduplicated in stable inventory order.

## Minimal start, stop and restart

```yaml
---
- name: Manage the example stack
  hosts: localhost
  gather_facts: false
  vars:
    serviceflow_action: restart
    serviceflow_services:
      - unit: postgresql.service
        groups: database

      - unit: example-api.service
        groups: application

      - unit: nginx.service
        groups: frontend
  roles:
    - role: mraibo.serviceflow.lifecycle
```

Start order:

```text
postgresql.service -> example-api.service -> nginx.service
```

Stop order:

```text
nginx.service -> example-api.service -> postgresql.service
```

A `restart` always performs the complete reverse-order stop phase followed by the complete declared-order start phase.

## Use an action passed on the command line

```yaml
---
- name: Manage the requested application lifecycle
  hosts: localhost
  gather_facts: false
  vars:
    serviceflow_action: "{{ requested_action | default('restart') }}"
    serviceflow_services:
      - unit: postgresql.service
        groups: database
      - unit: example-api.service
        groups: application
      - unit: nginx.service
        groups: frontend
  roles:
    - role: mraibo.serviceflow.lifecycle
```

Run it with:

```bash
ansible-playbook -i inventory.ini lifecycle.yml -e requested_action=start
ansible-playbook -i inventory.ini lifecycle.yml -e requested_action=stop
ansible-playbook -i inventory.ini lifecycle.yml -e requested_action=restart
```

Only `start`, `stop` and `restart` are accepted.

## Manage a multi-tier application

Use an explicit logical `name` when the display name should differ from the systemd unit. When `name` is omitted, ServiceFlow derives it from `unit` by removing only a final `.service` suffix.

```yaml
serviceflow_services:
  - name: primary-database
    unit: postgresql@main.service
    groups: database

  - name: business-api
    unit: company-example-api.service
    groups: application

  - name: public-frontend
    unit: nginx.service
    groups: frontend
```

Logical names must be unique. A target host and systemd unit combination may also appear only once in the resolved lifecycle.

## Target several inventory groups

`groups` accepts either one group name or a list.

```yaml
serviceflow_services:
  - unit: nginx.service
    groups:
      - frontend
      - edge
```

The concise form is equivalent:

```yaml
serviceflow_services:
  - unit: nginx.service
    groups: [frontend, edge]
```

If the same host belongs to both groups, ServiceFlow processes it only once for that service.

## Exclude maintenance hosts

`exclude_groups` removes hosts after the positive groups are merged.

```yaml
serviceflow_services:
  - unit: example-api.service
    groups: application
    exclude_groups: maintenance

  - unit: nginx.service
    groups: [frontend, edge]
    exclude_groups: [maintenance]
```

This is useful during rolling maintenance, incident isolation or staged deployments. Validation fails before the first service change when exclusion leaves a service without any target hosts.

## Skip optional services

`manage` must evaluate to a real boolean. A service with `manage: false` is skipped completely and appears in `serviceflow_result.skipped`.

```yaml
---
- name: Manage environment-specific services
  hosts: localhost
  gather_facts: false
  vars:
    environment_name: development
    serviceflow_action: restart
    serviceflow_services:
      - unit: postgresql.service
        groups: database

      - unit: example-api.service
        groups: application

      - unit: example-worker.service
        groups: application
        manage: "{{ environment_name == 'production' }}"
  roles:
    - role: mraibo.serviceflow.lifecycle
```

Do not use quoted boolean text such as:

```yaml
manage: "false"
```

That is a string, not a boolean, and is rejected deliberately.

## Wait for systemd readiness

Systemd readiness polls the unit until its `ActiveState` and, optionally, `SubState` match the expected values.

```yaml
serviceflow_services:
  - unit: postgresql.service
    groups: database
    ready:
      type: systemd
      active_state: active
      sub_state: running
      timeout: 90
      interval: 3
```

The concise default form waits for `ActiveState=active`:

```yaml
serviceflow_services:
  - unit: postgresql.service
    groups: database
    ready: {type: systemd}
```

Systemd readiness is checked even when the unit was already active before the playbook started.

## Wait for a new log message

Log readiness accepts only data written after the current real start transition. An old matching line already present in the file cannot produce a false success.

```yaml
serviceflow_services:
  - unit: example-api.service
    groups: application
    ready:
      type: log
      path: /var/log/example/api.log
      regex: '^Application ready on port [0-9]+$'
      timeout: 120
      interval: 1
```

The configured log path must be absolute. The regular expression uses Python regular-expression syntax.

Log readiness supports:

- a file that is created after startup;
- normal append operations;
- truncation or rewrite of the same file;
- rename-based rotation followed by creation of a new file at the configured path.

When the service is already active and no start transition occurs, the log readiness check is reported as skipped with reason `no_start_transition`.

## Run lifecycle hooks

Hooks are normal Ansible task files. They run only when their corresponding transition is actually required.

```yaml
serviceflow_services:
  - name: application
    unit: example-api.service
    groups: application
    hooks:
      before_start:
        - name: Prepare runtime directories
          tasks: hooks/prepare_runtime.yml

      before_stop:
        - name: Drain application traffic
          tasks: hooks/drain.yml

      after_ready:
        - name: Re-enable application traffic
          tasks: hooks/enable_traffic.yml

      after_stop:
        - name: Remove stale runtime files
          tasks: hooks/cleanup.yml
    ready:
      type: systemd
      active_state: active
      sub_state: running
```

Supported phases:

- `before_start`;
- `before_stop`;
- `after_ready`;
- `after_stop`.

`after_ready` requires a readiness definition and runs only after successful readiness following a real start transition. Hooks are not executed in check mode.

## Use hook variables and context

A hook can receive private values through `serviceflow_hook_vars`:

```yaml
serviceflow_services:
  - name: application
    unit: example-api.service
    groups: application
    hooks:
      before_stop:
        - name: Drain traffic
          tasks: hooks/drain.yml
          vars:
            drain_timeout: 45
            load_balancer_pool: example-production
```

Example `hooks/drain.yml`:

```yaml
---
- name: Show the lifecycle target
  ansible.builtin.debug:
    msg: >-
      Draining {{ serviceflow_hook_context.service }}
      on {{ serviceflow_hook_context.target_host }}
      for action {{ serviceflow_hook_context.action }}

- name: Wait for in-flight requests to finish
  ansible.builtin.command:
    argv:
      - /usr/local/bin/example-drain
      - --pool
      - "{{ serviceflow_hook_vars.load_balancer_pool }}"
      - --timeout
      - "{{ serviceflow_hook_vars.drain_timeout | string }}"
  changed_when: true
```

Hook task files receive this context:

```yaml
serviceflow_hook_context:
  action: restart
  phase: before_stop
  service: application
  unit: example-api.service
  target_host: app01.example.com
```

Hook variable names and values are omitted from the public lifecycle plan and structured result.

## Run without privilege escalation

Privilege escalation is enabled by default. Disable it only when the remote account is already permitted to manage the relevant unit and access readiness resources.

```yaml
---
- name: Manage user services without become
  hosts: localhost
  gather_facts: false
  vars:
    serviceflow_action: restart
    serviceflow_become: false
    serviceflow_services:
      - unit: example-user-service.service
        groups: application
  roles:
    - role: mraibo.serviceflow.lifecycle
```

ServiceFlow does not configure sudo, polkit or systemd permissions for you.

## Preview changes with check mode

```bash
ansible-playbook -i inventory.ini lifecycle.yml --check
```

Check mode:

- validates the complete lifecycle definition;
- asks `ansible.builtin.systemd_service` to predict transitions;
- does not run hooks;
- does not capture log boundaries;
- does not wait for future readiness events.

Use check mode before a production lifecycle change, but remember that it cannot prove that a future startup log message will appear.

## Display the redacted execution plan

```yaml
vars:
  serviceflow_show_plan: true
```

The displayed plan is intentionally redacted. Hook variable names and values are never exposed.

## Read the structured result

After the role finishes, `serviceflow_result` is available to later tasks in the same play.

```yaml
---
- name: Restart the application and inspect the result
  hosts: localhost
  gather_facts: false
  vars:
    serviceflow_action: restart
    serviceflow_services:
      - unit: postgresql.service
        groups: database
        ready: {type: systemd}
      - unit: example-api.service
        groups: application
        ready: {type: systemd}
  tasks:
    - name: Run ServiceFlow
      ansible.builtin.include_role:
        name: mraibo.serviceflow.lifecycle

    - name: Print the processed transitions
      ansible.builtin.debug:
        var: serviceflow_result.processed

    - name: Assert that the lifecycle completed
      ansible.builtin.assert:
        that:
          - serviceflow_result.schema_version == 1
          - serviceflow_result.action == serviceflow_action
          - serviceflow_result.check_mode == ansible_check_mode
```

The result contains these top-level fields:

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

The private execution plan is never returned.

## Keep service definitions in a separate file

For larger stacks, keep the lifecycle contract in a dedicated variables file.

`vars/services.yml`:

```yaml
---
serviceflow_services:
  - unit: postgresql.service
    groups: database
    ready: {type: systemd}

  - unit: example-api.service
    groups: application
    ready:
      type: log
      path: /var/log/example/api.log
      regex: '^Application ready$'
      timeout: 120
      interval: 1

  - unit: nginx.service
    groups: frontend
    ready: {type: systemd}
```

`lifecycle.yml`:

```yaml
---
- name: Manage the application lifecycle
  hosts: localhost
  gather_facts: false
  vars_files:
    - vars/services.yml
  vars:
    serviceflow_action: "{{ requested_action | default('restart') }}"
  roles:
    - role: mraibo.serviceflow.lifecycle
```

Run it with:

```bash
ansible-playbook -i inventory.ini lifecycle.yml -e requested_action=restart
```

## Complete production-style example

Directory layout:

```text
.
├── inventory.ini
├── lifecycle.yml
├── vars
│   └── production.yml
└── hooks
    ├── drain.yml
    └── enable_traffic.yml
```

`vars/production.yml`:

```yaml
---
environment_name: production

serviceflow_services:
  - name: database
    unit: postgresql@main.service
    groups: database
    ready:
      type: systemd
      active_state: active
      sub_state: running
      timeout: 120
      interval: 2

  - name: application
    unit: example-api.service
    groups: application
    exclude_groups: maintenance
    hooks:
      before_stop:
        - name: Drain application traffic
          tasks: hooks/drain.yml
          vars:
            timeout: 60
      after_ready:
        - name: Return application to service
          tasks: hooks/enable_traffic.yml
    ready:
      type: log
      path: /var/log/example/api.log
      regex: '^Application ready$'
      timeout: 180
      interval: 1

  - name: background-worker
    unit: example-worker.service
    groups: application
    exclude_groups: maintenance
    manage: "{{ environment_name == 'production' }}"
    ready: {type: systemd}

  - name: frontend
    unit: nginx.service
    groups: [frontend, edge]
    exclude_groups: maintenance
    ready:
      type: systemd
      active_state: active
      timeout: 60
      interval: 2
```

`lifecycle.yml`:

```yaml
---
- name: Manage the production application lifecycle
  hosts: localhost
  gather_facts: false
  vars_files:
    - vars/production.yml
  vars:
    serviceflow_action: "{{ requested_action | default('restart') }}"
    serviceflow_show_plan: "{{ show_plan | default(false) | bool }}"
  roles:
    - role: mraibo.serviceflow.lifecycle
```

Validate the lifecycle without changing services:

```bash
ansible-playbook -i inventory.ini lifecycle.yml \
  -e requested_action=restart \
  -e show_plan=true \
  --check
```

Perform the restart:

```bash
ansible-playbook -i inventory.ini lifecycle.yml \
  -e requested_action=restart
```

## Operational notes

- Run the role from exactly one orchestration host.
- Define services in their required start order; ServiceFlow derives stop order automatically.
- Use readiness checks for dependencies that must be operational before the next service starts.
- Use hooks for application-specific transition work, not for reimplementing systemd service management.
- Keep hook task files idempotent where practical.
- Test inventory group resolution and exclusion rules with `--check` before production changes.
- ServiceFlow stops at the first validation, hook, service or readiness failure.
- A service that starts successfully but fails readiness remains started; automatic rollback is not provided.
